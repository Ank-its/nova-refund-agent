"""Authentication routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_principal
from app.api.security import Principal, authenticate, issue_token
from app.db.session import get_db
from app.models.api import LoginRequest, LoginResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> LoginResponse:
    principal = await authenticate(body.username, body.password, db)
    return LoginResponse(
        token=issue_token(principal),
        username=principal.username,
        role=principal.role,
        has_customer_profile=principal.customer_id is not None,
    )


@router.get("/me", response_model=LoginResponse)
async def me(principal: Principal = Depends(current_principal)) -> LoginResponse:
    return LoginResponse(
        token="",
        username=principal.username,
        role=principal.role,
        has_customer_profile=principal.customer_id is not None,
    )
