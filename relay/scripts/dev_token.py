"""Mint a short-lived development token: uv run python -m scripts.dev_token c_77 [--staff]

Needs RELAY_AUTH_MODE=dev and RELAY_DEV_JWT_SECRET. Production uses tokens from a real identity provider.
"""

import argparse
import time

import jwt

from app.config import settings


def mint(sub: str, staff: bool = False, ttl_s: int = 3600, secret: str | None = None) -> str:
    now = int(time.time())
    claims = {
        "sub": sub,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + ttl_s,
        "roles": [settings.staff_role] if staff else [],
    }
    return jwt.encode(claims, secret or settings.dev_jwt_secret, algorithm="HS256")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("sub")
    ap.add_argument("--staff", action="store_true")
    args = ap.parse_args()
    print(mint(args.sub, args.staff))
