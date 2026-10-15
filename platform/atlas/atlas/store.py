"""Registry rules, in one place.

- A (kind, name, version) is immutable: a fix is a new version, so a digest pinned by a client never changes meaning.
- A name belongs to the team that first published it; another team cannot publish versions under it (no squatting).
- Any blocking finding rejects a submission automatically. Everything else waits for a human reviewer.
- Nobody approves their own submission, warnings must be acknowledged, and the eval gate (if set) must pass.
- Every state change is written to the audit log in the same transaction.
"""

from dataclasses import asdict

from psycopg import sql
from psycopg.types.json import Jsonb

from . import checks, metrics
from .auth import Principal
from .kinds import Parsed

FIELDS = sql.SQL(
    "id, kind, name, version, team_id, status, source, title, description, tags, license, document, digest, eval, "
    "submitted_by, reviewed_by, reviewed_at, review_note, created_at"
)


class Conflict(Exception):
    pass


class Forbidden(Exception):
    pass


async def audit(c, actor: str, action: str, target: str, details: dict | None = None) -> None:
    await c.execute(
        "INSERT INTO audit (actor, action, target, details) VALUES (%s, %s, %s, %s)",
        (actor, action, target, Jsonb(details or {})),
    )


def target(kind: str, name: str, version: str) -> str:
    return f"{kind}/{name}@{version}"


async def publish(
    pool, p: Parsed, who: Principal, team_id: str | None, eval_report: dict | None, cfg, source: str = "internal"
) -> dict:
    found = checks.run(p, cfg.licenses_allowed, cfg.require_auth_on_agents)
    blocked = [f for f in found if f.severity == "block"]
    status = "rejected" if blocked else "in_review"
    note = "automatically rejected: " + "; ".join(f"{f.message} ({f.location})" for f in blocked) if blocked else None
    async with pool.connection() as c, c.transaction():
        owner = await (
            await c.execute(
                "SELECT team_id FROM artifacts WHERE kind = %s AND name = %s AND team_id IS NOT NULL LIMIT 1",
                (p.kind, p.name),
            )
        ).fetchone()
        if owner and team_id and owner["team_id"] != team_id:
            raise Forbidden(f"{p.name} belongs to team {owner['team_id']}")
        exists = await (
            await c.execute(
                "SELECT 1 FROM artifacts WHERE kind = %s AND name = %s AND version = %s", (p.kind, p.name, p.version)
            )
        ).fetchone()
        if exists:
            raise Conflict(f"{target(p.kind, p.name, p.version)} already exists; publish a new version")
        row = await (
            await c.execute(
                sql.SQL(
                    "INSERT INTO artifacts (kind, name, version, team_id, status, source, title, description, tags, "
                    "license, document, digest, package, eval, submitted_by, review_note) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING {}"
                ).format(FIELDS),
                (
                    p.kind,
                    p.name,
                    p.version,
                    team_id,
                    status,
                    source,
                    p.title,
                    p.description,
                    p.tags,
                    p.license,
                    Jsonb(p.document),
                    p.digest,
                    p.blob,
                    Jsonb(eval_report) if eval_report else None,
                    who.id,
                    note,
                ),
            )
        ).fetchone()
        for f in found:
            await c.execute(
                "INSERT INTO findings (artifact_id, check_name, severity, message, location) VALUES (%s, %s, %s, %s, %s)",
                (row["id"], f.check, f.severity, f.message, f.location),
            )
        await audit(c, who.id, "publish", target(p.kind, p.name, p.version), {"status": status, "digest": p.digest})
    metrics.submissions.labels(kind=p.kind, outcome=status).inc()
    return row | {"findings": [asdict(f) for f in found]}


async def get(pool, kind: str, name: str, version: str) -> dict | None:
    async with pool.connection() as c:
        row = await (
            await c.execute(
                sql.SQL("SELECT {} FROM artifacts WHERE kind = %s AND name = %s AND version = %s").format(FIELDS),
                (kind, name, version),
            )
        ).fetchone()
        if not row:
            return None
        found = await (
            await c.execute(
                "SELECT check_name AS check, severity, message, location FROM findings WHERE artifact_id = %s",
                (row["id"],),
            )
        ).fetchall()
    return row | {"findings": found}


async def review(pool, kind, name, version, who: Principal, approve: bool, note: str, acknowledge: bool, cfg) -> dict:
    art = await get(pool, kind, name, version)
    if not art:
        raise LookupError(target(kind, name, version))
    if art["status"] != "in_review":
        raise Conflict(f"only submissions in review can be decided; this one is {art['status']}")
    if art["submitted_by"] == who.id:
        raise Forbidden("you cannot review your own submission")
    if approve:
        if any(f["severity"] == "warn" for f in art["findings"]) and not acknowledge:
            raise Conflict("this submission has warnings: read them and pass acknowledge_warnings=true to approve")
        if cfg.eval_min_score is not None:
            score = (art["eval"] or {}).get("score")
            if not isinstance(score, int | float) or score < cfg.eval_min_score:
                raise Conflict(f"approval needs an eval report scoring at least {cfg.eval_min_score}")
    status = "approved" if approve else "rejected"
    async with pool.connection() as c, c.transaction():
        row = await (
            await c.execute(
                sql.SQL(
                    "UPDATE artifacts SET status = %s, reviewed_by = %s, reviewed_at = now(), review_note = %s "
                    "WHERE id = %s AND status = 'in_review' RETURNING {}"
                ).format(FIELDS),
                (status, who.id, note, art["id"]),
            )
        ).fetchone()
        if not row:
            raise Conflict("another reviewer decided this submission first")
        await audit(c, who.id, "approve" if approve else "reject", target(kind, name, version), {"note": note})
    metrics.reviews.labels(kind=kind, decision=status).inc()
    return row


async def deprecate(pool, kind, name, version, who: Principal, note: str) -> dict:
    art = await get(pool, kind, name, version)
    if not art:
        raise LookupError(target(kind, name, version))
    if not (who.can("admin") or (who.can("publisher") and who.team_id and who.team_id == art["team_id"])):
        raise Forbidden("only the owning team or an admin can deprecate")
    if art["status"] != "approved":
        raise Conflict("only approved versions can be deprecated")
    async with pool.connection() as c, c.transaction():
        row = await (
            await c.execute(
                sql.SQL(
                    "UPDATE artifacts SET status = 'deprecated', review_note = %s WHERE id = %s RETURNING {}"
                ).format(FIELDS),
                (note, art["id"]),
            )
        ).fetchone()
        await audit(c, who.id, "deprecate", target(kind, name, version), {"note": note})
    return row


async def search(pool, q: str | None, kind: str | None, statuses: list[str], team: str | None, limit: int) -> list:
    where, args = [sql.SQL("status = ANY(%s)")], [statuses]
    if kind:
        where.append(sql.SQL("kind = %s"))
        args.append(kind)
    if team:
        where.append(sql.SQL("team_id = %s"))
        args.append(team)
    rank, rank_args = sql.SQL("0"), []
    if q:
        where.append(sql.SQL("search @@ websearch_to_tsquery('english', %s)"))
        args.append(q)
        rank, rank_args = sql.SQL("ts_rank(search, websearch_to_tsquery('english', %s))"), [q]
    query = sql.SQL(
        "SELECT kind, name, version, status, team_id, title, description, tags, digest, created_at, {} AS rank "
        "FROM artifacts WHERE {} ORDER BY rank DESC, name, created_at DESC LIMIT %s"
    ).format(rank, sql.SQL(" AND ").join(where))
    async with pool.connection() as c:
        return await (await c.execute(query, rank_args + args + [limit])).fetchall()
