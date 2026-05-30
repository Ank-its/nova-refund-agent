"""Conversation + message persistence (all scoped to a user)."""
from __future__ import annotations

import uuid

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.schema import Conversation, Message


async def list_conversations(session: AsyncSession, user_id: uuid.UUID) -> list[Conversation]:
    rows = await session.scalars(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(desc(Conversation.updated_at))
    )
    return list(rows.all())


async def create_conversation(
    session: AsyncSession, user_id: uuid.UUID, title: str = "New conversation"
) -> Conversation:
    conv = Conversation(user_id=user_id, title=title)
    session.add(conv)
    await session.flush()
    return conv


async def get_conversation(
    session: AsyncSession, user_id: uuid.UUID, conv_id: uuid.UUID
) -> Conversation | None:
    return await session.scalar(
        select(Conversation).where(
            Conversation.id == conv_id, Conversation.user_id == user_id
        )
    )


async def get_messages(session: AsyncSession, conv_id: uuid.UUID) -> list[Message]:
    # UUID PKs aren't sequential — order by creation time (id as tiebreak).
    rows = await session.scalars(
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at, Message.id)
    )
    return list(rows.all())


async def count_messages(session: AsyncSession, conv_id: uuid.UUID) -> int:
    return (
        await session.scalar(
            select(func.count(Message.id)).where(Message.conversation_id == conv_id)
        )
        or 0
    )


async def add_message(
    session: AsyncSession,
    conv_id: uuid.UUID,
    role: str,
    content: str,
    *,
    decision: str | None = None,
    rule: str | None = None,
    steps: list | None = None,
) -> Message:
    msg = Message(
        conversation_id=conv_id,
        role=role,
        content=content,
        decision=decision,
        rule=rule,
        steps=steps or [],
    )
    session.add(msg)
    return msg
