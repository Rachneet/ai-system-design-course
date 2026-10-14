"""Virtual keys: sbk_<id>_<secret>. Only a SHA-256 of the full key is stored; lookups are by id, then a
constant-time hash comparison. Verified keys are cached briefly per instance."""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from psycopg_pool import AsyncConnectionPool


@dataclass(frozen=True)
class Caller:
    key_id: str
    app_id: str
    team_id: str
    org_id: str
    allowed_models: tuple[str, ...]
    rpm: int
    tpm: int
    pii_mode: str
    log_bodies: bool
    retention_days: int


def new_key() -> tuple[str, str, str]:
    """Returns (key_id, plaintext key shown once, hash to store)."""
    key_id = secrets.token_hex(6)
    plaintext = f"sbk_{key_id}_{secrets.token_urlsafe(32)}"
    return key_id, plaintext, hash_key(plaintext)


def hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


LOOKUP = """
SELECT k.id AS key_id, k.secret_hash, a.id AS app_id, t.id AS team_id, o.id AS org_id, a.allowed_models,
       a.rpm, a.tpm, a.pii_mode, a.log_bodies, a.retention_days
FROM api_keys k JOIN apps a ON a.id = k.app_id JOIN teams t ON t.id = a.team_id JOIN orgs o ON o.id = t.org_id
WHERE k.id = %s AND k.revoked_at IS NULL AND (k.expires_at IS NULL OR k.expires_at > now())
"""


class KeyStore:
    def __init__(self, pool: AsyncConnectionPool, ttl_s: float, clock=time.monotonic):
        self.pool, self.ttl_s, self.clock = pool, ttl_s, clock
        self._cache: dict[str, tuple[float, Caller]] = {}

    async def verify(self, presented: str | None) -> Caller | None:
        if not presented or not presented.startswith("sbk_") or presented.count("_") < 2:
            return None
        key_id = presented.split("_", 2)[1]
        digest = hash_key(presented)
        cached = self._cache.get(digest)
        if cached and self.clock() - cached[0] < self.ttl_s:
            return cached[1]
        async with self.pool.connection() as c:
            row = await (await c.execute(LOOKUP, (key_id,))).fetchone()
        if row is None or not hmac.compare_digest(row["secret_hash"], digest):
            return None
        caller = Caller(
            row["key_id"],
            row["app_id"],
            row["team_id"],
            row["org_id"],
            tuple(row["allowed_models"]),
            row["rpm"],
            row["tpm"],
            row["pii_mode"],
            row["log_bodies"],
            row["retention_days"],
        )
        self._cache[digest] = (self.clock(), caller)
        return caller

    def forget(self, key_id: str | None = None) -> None:
        """Drop cached verifications (all, or one key's) after a revocation or an app policy change."""
        if key_id is None:
            self._cache.clear()
        else:
            self._cache = {d: v for d, v in self._cache.items() if v[1].key_id != key_id}
