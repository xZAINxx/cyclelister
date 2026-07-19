"""Supabase JWT auth as a FastAPI dependency (spec §15: least privilege).

Modes, selected by config:
- AUTH_REQUIRED=false (default): dev bypass — requests run as a fixed dev user
  so local development needs no Supabase account.
- AUTH_REQUIRED=true + SUPABASE_JWT_SECRET set: legacy HS256 verification.
- AUTH_REQUIRED=true + SUPABASE_URL set (no secret): ES256/RS256 via the
  project's public JWKS endpoint — no shared secret to manage at all.
"""
import asyncio
import uuid

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import User
from app.db.session import get_db

_DEV_SUB = "dev-user"
_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def _jwks_client(supabase_url: str) -> jwt.PyJWKClient:
    url = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    if url not in _jwks_clients:
        _jwks_clients[url] = jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)
    return _jwks_clients[url]


def _decode_jwks(token: str, settings: Settings) -> dict:
    """Blocking (urllib inside PyJWKClient) — always call via asyncio.to_thread."""
    signing_key = _jwks_client(settings.supabase_url).get_signing_key_from_jwt(token)
    return jwt.decode(
        token, signing_key.key, algorithms=["ES256", "RS256"], audience="authenticated"
    )


async def _get_or_create_user(db: AsyncSession, sub: str, email: str | None) -> User:
    user = (await db.execute(select(User).where(User.supabase_sub == sub))).scalar_one_or_none()
    if user is None:
        user = User(supabase_sub=sub, email=email, role="owner")
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    if not settings.auth_required:
        return await _get_or_create_user(db, _DEV_SUB, "dev@localhost")

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth.removeprefix("Bearer ").strip()

    try:
        if settings.supabase_jwt_secret:
            claims = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        elif settings.supabase_url:
            claims = await asyncio.to_thread(_decode_jwks, token, settings)
        else:
            raise HTTPException(
                status_code=500,
                detail="AUTH_REQUIRED is set but neither SUPABASE_JWT_SECRET nor SUPABASE_URL is configured",
            )
    except HTTPException:
        raise
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception:
        raise HTTPException(status_code=401, detail="Token verification failed")

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        uuid.UUID(sub)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid subject")
    return await _get_or_create_user(db, sub, claims.get("email"))
