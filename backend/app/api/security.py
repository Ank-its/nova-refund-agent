"""Stateless, signed bearer tokens + principal loading.

Tokens are HMAC-signed and carry only the user id (a UUID) — there is no
server-side session store, so sessions survive backend restarts and redeploys
(as long as ``secret_key`` is stable). Each request re-verifies the signature
and reloads the principal from the database, so role/profile changes take
effect immediately and a tampered token is rejected.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import verify_password
from app.db.schema import Customer, User


@dataclass
class Principal:
    user_id: uuid.UUID
    username: str
    role: str
    customer_id: uuid.UUID | None  # None for admin-only accounts


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _sign(payload: str) -> str:
    secret = get_settings().secret_key.encode()
    sig = hmac.new(secret, payload.encode(), hashlib.sha256).digest()
    return _b64(sig)


def issue_token(principal: Principal) -> str:
    """Return ``<user_id>.<hmac-sig>`` — verifiable without any server state."""
    payload = str(principal.user_id)
    return f"{payload}.{_sign(payload)}"


def _verify_token(token: str) -> uuid.UUID | None:
    """Return the user id if the signature is valid, else None."""
    try:
        payload, sig = token.rsplit(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    try:
        return uuid.UUID(payload)
    except ValueError:
        return None


async def _load_principal(user_id: uuid.UUID, db: AsyncSession) -> Principal | None:
    user = await db.get(User, user_id)
    if user is None:
        return None
    customer = await db.scalar(select(Customer).where(Customer.user_id == user.id))
    return Principal(
        user_id=user.id,
        username=user.username,
        role=user.role,
        customer_id=customer.id if customer else None,
    )


async def principal_from_token(token: str, db: AsyncSession) -> Principal | None:
    user_id = _verify_token(token)
    if user_id is None:
        return None
    return await _load_principal(user_id, db)


async def authenticate(username: str, password: str, db: AsyncSession) -> Principal:
    user = await db.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    customer = await db.scalar(select(Customer).where(Customer.user_id == user.id))
    return Principal(
        user_id=user.id,
        username=user.username,
        role=user.role,
        customer_id=customer.id if customer else None,
    )
