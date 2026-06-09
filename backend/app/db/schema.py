"""Consolidated database schema — every SQLAlchemy ORM table in one file.

This is the single source of truth for the relational schema (entities,
constraints, indexes). The engine/session/Base live in ``app.db.session``;
this module defines the tables on that ``Base`` and is imported by Alembic to
populate ``Base.metadata``.

Entities:
  User          -> auth: credentials, unique key, role mapping
  Customer      -> profile: loyalty tier, 1:1 with a user
  Order         -> purchase log: amount, date, clearance flag
  Refund        -> settlement: status + reason; UNIQUE(order_id) idempotency
  Conversation  -> chat thread + multi-turn agent state (survives restarts)
  Message       -> a persisted turn within a conversation
  ToolAuditLog  -> immutable per-tool-call telemetry for the admin dashboard

All ids and foreign keys are UUIDs (application-generated, stable across DBs).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import LOYALTY_TIERS, REFUND_STATUSES, ROLES
from app.db.session import Base


# --- shared helpers ---------------------------------------------------------
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def uuid_pk() -> Mapped[uuid.UUID]:
    """A UUID primary key generated application-side (stable across DBs)."""
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


# --- tables -----------------------------------------------------------------
class User(Base):
    """Authentication Storage: credentials, unique key, role mapping."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint(f"role IN {ROLES}", name="ck_users_role"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="customer")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    customer: Mapped["Customer | None"] = relationship(
        back_populates="user", uselist=False
    )


class Customer(Base):
    """Customer Profile Tracking: maps a user to loyalty tier and details."""

    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint(f"loyalty_tier IN {LOYALTY_TIERS}", name="ck_customers_tier"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    full_name: Mapped[str] = mapped_column(String(128))
    email: Mapped[str] = mapped_column(String(128), unique=True)
    loyalty_tier: Mapped[str] = mapped_column(String(16), default="standard")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="customer")
    orders: Mapped[list["Order"]] = relationship(back_populates="customer")
    refunds: Mapped[list["Refund"]] = relationship(back_populates="customer")


class Order(Base):
    """Purchase Log History: dates, financial value, item, clearance flag."""

    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = uuid_pk()
    order_ref: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    item_name: Mapped[str] = mapped_column(String(160))
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    purchase_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_final_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    customer: Mapped["Customer"] = relationship(back_populates="orders")
    refund: Mapped["Refund | None"] = relationship(
        back_populates="order", uselist=False
    )


class Refund(Base):
    """Refund Settlement Records.

    The UNIQUE constraint on ``order_id`` is the database-level single-refund
    idempotency guard: a second refund row for the same order is impossible.
    """

    __tablename__ = "refunds"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_refunds_order_id"),
        CheckConstraint(f"status IN {REFUND_STATUSES}", name="ck_refunds_status"),
        Index("ix_refunds_customer_status", "customer_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("orders.id", ondelete="CASCADE")
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(255), default="")
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    decision_detail: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    order: Mapped["Order"] = relationship(back_populates="refund")
    customer: Mapped["Customer"] = relationship(back_populates="refunds")


class Conversation(Base):
    """Chat thread scoped to a user.

    Multi-turn agent state is reconstructed by replaying the persisted messages
    into the agent each turn, so no in-flight state is stored on this row.
    """

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(120), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    """A persisted turn (user or assistant) within a conversation."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rule: Mapped[str | None] = mapped_column(String(40), nullable=True)
    steps: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class ToolAuditLog(Base):
    """Immutable per-tool-call telemetry, surfaced in the admin dashboard."""

    __tablename__ = "tool_audit_log"

    id: Mapped[uuid.UUID] = uuid_pk()
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tool_name: Mapped[str] = mapped_column(String(64))
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


__all__ = [
    "utcnow",
    "uuid_pk",
    "User",
    "Customer",
    "Order",
    "Refund",
    "Conversation",
    "Message",
    "ToolAuditLog",
]
