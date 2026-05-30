"""Request/response DTOs for the HTTP API."""
from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    role: str
    has_customer_profile: bool


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class ConversationSummary(BaseModel):
    id: str
    title: str
    updated_at: str


class MessageOut(BaseModel):
    role: str
    content: str
    decision: str | None = None
    rule: str | None = None
    steps: list[str] = []
