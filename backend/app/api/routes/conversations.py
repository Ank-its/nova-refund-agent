"""Conversation history routes (list, create, fetch messages)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_principal
from app.api.security import Principal
from app.db.session import get_db
from app.models.api import ConversationSummary, MessageOut
from app.services.conversations import (
    create_conversation,
    get_conversation,
    get_messages,
    list_conversations,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationSummary])
async def list_all(
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationSummary]:
    convs = await list_conversations(db, principal.user_id)
    return [
        ConversationSummary(
            id=str(c.id), title=c.title, updated_at=c.updated_at.isoformat()
        )
        for c in convs
    ]


@router.post("", response_model=ConversationSummary)
async def create(
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
) -> ConversationSummary:
    conv = await create_conversation(db, principal.user_id)
    await db.commit()
    return ConversationSummary(
        id=str(conv.id), title=conv.title, updated_at=conv.updated_at.isoformat()
    )


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def messages(
    conversation_id: uuid.UUID,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[MessageOut]:
    conv = await get_conversation(db, principal.user_id, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    rows = await get_messages(db, conversation_id)
    return [
        MessageOut(
            role=m.role,
            content=m.content,
            decision=m.decision,
            rule=m.rule,
            steps=list(m.steps or []),
        )
        for m in rows
    ]
