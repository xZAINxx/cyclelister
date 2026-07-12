"""Supabase JWT auth as a FastAPI dependency.

Dev mode: when SUPABASE_JWT_SECRET is empty, requests run as a fixed dev user
so the app is usable locally without a Supabase project.
"""
import uuid

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import User
from app.db.session import get_db

_DEV_SUB = "dev-user"


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
    if not settings.supabase_jwt_secret:
        return await _get_or_create_user(db, _DEV_SUB, "dev@localhost")

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth.removeprefix("Bearer ").strip()
    try:
        claims = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        uuid.UUID(sub)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid subject")
    return await _get_or_create_user(db, sub, claims.get("email"))
