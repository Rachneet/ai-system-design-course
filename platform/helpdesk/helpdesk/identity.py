"""The people. Staff sign in with company SSO and customers with the store's customer identity; both arrive as a JWT
whose `tenant` claim says which desk they belong to. The same token travels to Checkpoint as X-User-Token, so it
names both audiences (ADR 0003). In development, POST /dev/token mints HS256 tokens; production verifies the
identity provider's RS256 or ES256 keys."""

import time
from dataclasses import dataclass, field

import jwt

AUDIENCES = ["helpdesk", "checkpoint"]


@dataclass(frozen=True)
class User:
    id: str
    tenant: str
    roles: tuple[str, ...]
    name: str = ""
    token: str = field(default="", repr=False)

    def has(self, role: str) -> bool:
        return role in self.roles


class Users:
    def __init__(self, cfg, tenants):
        self.cfg, self.tenants = cfg, set(tenants)
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
        if claims.get("tenant") not in self.tenants:
            raise jwt.InvalidTokenError("the token names no known tenant")
        roles = tuple(r for r in claims.get("roles") or [] if isinstance(r, str))
        return User(str(claims["sub"]), claims["tenant"], roles, str(claims.get("name", "")), token)


def mint(secret: str, sub: str, tenant: str, roles=(), name: str = "", ttl_s: int = 3600) -> str:
    now = int(time.time())
    claims = {"sub": sub, "tenant": tenant, "roles": list(roles), "name": name, "aud": AUDIENCES, "iat": now}
    return jwt.encode(claims | {"exp": now + ttl_s}, secret, "HS256")


def expired(token: str, leeway_s: int = 30) -> bool:
    """For a stored token: has it lapsed (or will within leeway)? Signature checks happen where it is used."""
    try:
        exp = jwt.decode(token, options={"verify_signature": False}).get("exp", 0)
    except jwt.PyJWTError:
        return True
    return exp <= time.time() + leeway_s
