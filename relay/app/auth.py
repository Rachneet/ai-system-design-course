"""Authentication: who is calling, decided only from a verified token. The model never influences identity."""

from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    customer_id: str
    staff: bool = False


class Verifier:
    def __init__(self, cfg: Settings, jwks_client: jwt.PyJWKClient | None = None):
        self.cfg = cfg
        if cfg.auth_mode == "jwt":
            if not (cfg.jwks_url and cfg.jwt_issuer):
                raise RuntimeError("auth_mode=jwt needs RELAY_JWKS_URL and RELAY_JWT_ISSUER")
            self.jwks = jwks_client or jwt.PyJWKClient(cfg.jwks_url, cache_keys=True)
        elif cfg.auth_mode == "dev":
            if len(cfg.dev_jwt_secret) < 32:
                raise RuntimeError("auth_mode=dev needs RELAY_DEV_JWT_SECRET of at least 32 characters")
        else:
            raise RuntimeError(f"unknown auth_mode {cfg.auth_mode!r}")

    def verify(self, token: str) -> Principal:
        try:
            if self.cfg.auth_mode == "jwt":
                key = self.jwks.get_signing_key_from_jwt(token).key
                claims = jwt.decode(
                    token,
                    key,
                    algorithms=["RS256", "ES256"],
                    audience=self.cfg.jwt_audience,
                    issuer=self.cfg.jwt_issuer,
                    options={"require": ["exp", "sub"]},
                )
            else:
                claims = jwt.decode(
                    token,
                    self.cfg.dev_jwt_secret,
                    algorithms=["HS256"],
                    audience=self.cfg.jwt_audience,
                    options={"require": ["exp", "sub"]},
                )
        except jwt.PyJWTError as e:
            raise HTTPException(
                401, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"}
            ) from e
        return Principal(customer_id=str(claims["sub"]), staff=self.cfg.staff_role in claims.get("roles", []))


_verifier: Verifier | None = None


def get_verifier() -> Verifier:
    global _verifier
    if _verifier is None:
        _verifier = Verifier(settings)
    return _verifier


async def current_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), verifier: Verifier = Depends(get_verifier)
) -> Principal:
    if creds is None:
        raise HTTPException(401, "Missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    return verifier.verify(creds.credentials)


async def staff_only(principal: Principal = Depends(current_principal)) -> Principal:
    if not principal.staff:
        raise HTTPException(403, "Staff only")
    return principal
