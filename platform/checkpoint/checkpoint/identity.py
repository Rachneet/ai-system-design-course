"""Who is calling. Agents authenticate with their own token (ckp_<id>_<secret>, only a hash stored). The end user
the agent acts for arrives as a JWT in X-User-Token and is verified here, never trusted as a plain header.
Upstream servers then receive a short-lived assertion signed by Checkpoint naming both: sub is the user, act.sub
the agent (the RFC 8693 actor claim), aud the server. Agents never hold upstream credentials."""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


@dataclass(frozen=True)
class Agent:
    id: str
    role: str  # agent | approver


@dataclass(frozen=True)
class User:
    id: str
    roles: tuple[str, ...]


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def new_token() -> tuple[str, str, str]:
    tid, secret = secrets.token_hex(6), secrets.token_urlsafe(32)
    return tid, f"ckp_{tid}_{secret}", digest(secret)


async def resolve(pool, presented: str) -> Agent | None:
    parts = presented.split("_", 2)
    if len(parts) != 3 or parts[0] != "ckp":
        return None
    async with pool.connection() as c:
        row = await (
            await c.execute("SELECT id, role, token_hash FROM agents WHERE id = %s AND revoked_at IS NULL", (parts[1],))
        ).fetchone()
    if not row or not hmac.compare_digest(row["token_hash"], digest(parts[2])):
        return None
    return Agent(row["id"], row["role"])


class UserVerifier:
    def __init__(self, cfg):
        self.cfg = cfg
        self.jwks = jwt.PyJWKClient(cfg.user_jwks_url) if cfg.user_jwks_url else None

    def verify(self, token: str) -> User:
        opts = {"audience": self.cfg.user_jwt_audience, "options": {"require": ["exp", "sub"]}}
        if self.cfg.user_jwt_issuer:
            opts["issuer"] = self.cfg.user_jwt_issuer
        if self.jwks:
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256", "ES256"], **opts)
        elif self.cfg.user_jwt_secret:
            claims = jwt.decode(token, self.cfg.user_jwt_secret, algorithms=["HS256"], **opts)
        else:
            raise jwt.InvalidTokenError("no user token verification configured")
        roles = claims.get("roles") or []
        return User(str(claims["sub"]), tuple(r for r in roles if isinstance(r, str)))


class Signer:
    def __init__(self, pem: str, ttl_s: int):
        if pem:
            self.key = serialization.load_pem_private_key(pem.encode(), password=None)
        else:
            self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)  # development only
        self.kid = hashlib.sha256(
            self.key.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
            )
        ).hexdigest()[:16]
        self.ttl_s = ttl_s

    def jwks(self) -> dict:
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key(), as_dict=True)
        return {"keys": [jwk | {"kid": self.kid, "use": "sig", "alg": "RS256"}]}

    def assertion(self, server: str, tool: str, agent: Agent, user: User | None) -> str:
        now = int(time.time())
        claims = {
            "iss": "checkpoint",
            "aud": server,
            "sub": user.id if user else f"agent:{agent.id}",
            "act": {"sub": agent.id},
            "tool": tool,
            "iat": now,
            "exp": now + self.ttl_s,
            "jti": secrets.token_hex(8),
        }
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": self.kid})
