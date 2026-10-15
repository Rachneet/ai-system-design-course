"""Bearer tokens `atk_<id>_<secret>`: only a SHA-256 of the secret is stored. Roles: admin, reviewer, publisher,
reader. Publishers act for one team; reviewers approve; nobody approves their own submission."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request

ROLES = {"admin", "reviewer", "publisher", "reader"}


@dataclass(frozen=True)
class Principal:
    id: str
    team_id: str | None
    roles: frozenset[str]

    def can(self, role: str) -> bool:
        return "admin" in self.roles or role in self.roles


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def new_token() -> tuple[str, str, str]:
    """Returns (token id, plaintext token shown once, stored hash)."""
    tid, secret = secrets.token_hex(6), secrets.token_urlsafe(32)
    return tid, f"atk_{tid}_{secret}", digest(secret)


async def principal(request: Request, authorization: str = Header(default="")) -> Principal | None:
    presented = authorization.removeprefix("Bearer ").strip()
    if not presented:
        return None
    admin = request.app.state.settings.admin_token
    if admin and hmac.compare_digest(digest(presented), digest(admin)):
        return Principal("bootstrap-admin", None, frozenset({"admin"}))
    parts = presented.split("_", 2)
    if len(parts) != 3 or parts[0] != "atk":
        return None
    async with request.app.state.pool.connection() as c:
        row = await (
            await c.execute(
                "SELECT id, team_id, roles, token_hash FROM principals WHERE id = %s AND revoked_at IS NULL",
                (parts[1],),
            )
        ).fetchone()
    if not row or not hmac.compare_digest(row["token_hash"], digest(parts[2])):
        return None
    return Principal(row["id"], row["team_id"], frozenset(row["roles"]))


def require(role: str):
    async def dep(who: Principal | None = Depends(principal)) -> Principal:
        if who is None:
            raise HTTPException(401, "A valid Atlas token is required")
        if not who.can(role):
            raise HTTPException(403, f"This needs the {role} role")
        return who

    return dep


async def authenticated(who: Principal | None = Depends(principal)) -> Principal:
    if who is None:
        raise HTTPException(401, "A valid Atlas token is required")
    return who


async def reader(request: Request, who: Principal | None = Depends(principal)) -> Principal | None:
    if who is None and not request.app.state.settings.public_read:
        raise HTTPException(401, "A valid Atlas token is required")
    return who
