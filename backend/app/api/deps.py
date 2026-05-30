"""FastAPI dependencies for auth and role gating."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import Principal, principal_from_token
from app.db.session import get_db


async def current_principal(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    principal = await principal_from_token(authorization.split(" ", 1)[1].strip(), db)
    if principal is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return principal


def require_admin(principal: Principal = Depends(current_principal)) -> Principal:
    if principal.role not in ("admin", "superuser"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return principal
