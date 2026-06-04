"""FastAPI dependencies — JWT verification against Supabase's public JWKS.

Supabase publishes its JWT signing keys at
`<project-url>/auth/v1/.well-known/jwks.json` (RS256 in current projects, with
ES256 supported for projects that opt in). We fetch + cache the JWKS once per
process; PyJWKClient re-fetches automatically when a token's `kid` header
isn't in the cache, which covers key-rotation cases.

This deliberately replaces the older HS256-with-shared-secret approach.
Asymmetric verification means the server never needs the JWT signing secret —
the public key is, well, public — so there's nothing to leak and nothing to
rotate in our config when Supabase rotates keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt import PyJWKClient

from app.config import Settings, get_settings


# One JWKS client per project URL. `lifespan` is the PyJWKClient cache TTL —
# 10 minutes is a safe default; lookups for an unknown `kid` force a refresh
# anyway, so set-and-forget is fine here.
@lru_cache(maxsize=1)
def _jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True, lifespan=600)


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str | None


def require_user(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> AuthUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        signing_key = _jwks_client(settings.supabase_jwks_url).get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            # Supabase issues RS256 by default; ES256 is allowed for projects
            # that explicitly chose it. We accept both rather than ship two
            # different code paths.
            algorithms=["RS256", "ES256"],
            audience="authenticated",
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}") from e

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token missing sub")
    return AuthUser(id=sub, email=payload.get("email"))
