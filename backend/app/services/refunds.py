"""The state-mutating refund service: atomic, idempotent, deterministic."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.schema import Order, Refund, utcnow
from app.models.decision import RuleDecision
from app.services.audit import log_tool_call
from app.services.rules import evaluate_rules


@dataclass
class Step:
    """A masked progress step, surfaced to chat + telemetry."""

    label: str
    detail: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class RefundOutcome:
    decision: RuleDecision
    steps: list[Step]
    order: dict  # snapshot ({} if not found)


async def process_refund(
    session: AsyncSession, *, customer_id: uuid.UUID, order_ref: str, reason: str
) -> RefundOutcome:
    """Resolve -> lock -> evaluate -> (maybe) mutate, atomically.

    A row is persisted only for approved/pending_review outcomes; the
    UNIQUE(order_id) constraint is the last-line idempotency guard against
    concurrent double-submits.
    """
    settings = get_settings()
    t0 = time.perf_counter()
    steps = [Step("🔍 Locating your order", f"order_ref={order_ref}")]

    order = await session.scalar(
        select(Order)
        .where(Order.order_ref == order_ref, Order.customer_id == customer_id)
        .with_for_update()
    )
    if order is None:
        decision = RuleDecision(
            decision="rejected",
            rule="order_not_found",
            summary="No order with that reference exists on this account.",
            detail=f"no order {order_ref} for customer {customer_id}.",
        )
        await log_tool_call(
            customer_id=customer_id, tool_name="process_refund",
            arguments={"order_ref": order_ref, "reason": reason},
            result=decision.model_dump(),
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
        return RefundOutcome(decision, steps, {})

    snapshot = {
        "order_ref": order.order_ref,
        "item_name": order.item_name,
        "amount": float(order.amount),
        "is_final_sale": order.is_final_sale,
        "purchase_date": order.purchase_date.isoformat(),
    }
    steps.append(Step("📦 Checking item eligibility", f"final_sale={order.is_final_sale}"))

    existing = await session.scalar(select(Refund).where(Refund.order_id == order.id))
    days_since = (utcnow() - order.purchase_date).days
    steps.append(Step("🗓️ Verifying purchase date", f"days_since_purchase={days_since}"))

    approved_30d = (
        await session.scalar(
            select(func.count(Refund.id)).where(
                Refund.customer_id == customer_id,
                Refund.status == "approved",
                Refund.created_at >= utcnow() - timedelta(days=settings.velocity_window_days),
            )
        )
        or 0
    )
    steps.append(Step("🛡️ Running fraud/velocity checks", f"approved_refunds_30d={approved_30d}"))

    steps.append(Step("🧮 Applying refund policy", "evaluating rule matrix"))
    decision = evaluate_rules(
        is_final_sale=order.is_final_sale,
        already_refunded=existing is not None,
        days_since_purchase=days_since,
        amount=float(order.amount),
        approved_refunds_30d=approved_30d,
        reason=reason,
        settings=settings,
    )

    if decision.decision in ("approved", "pending_review"):
        session.add(
            Refund(
                order_id=order.id,
                customer_id=customer_id,
                status=decision.decision,
                reason=(reason or "")[:255],
                amount=order.amount,
                decision_detail=decision.rule,
            )
        )
        try:
            await session.commit()
            steps.append(Step("💾 Recording decision", f"status={decision.decision}"))
        except IntegrityError:
            await session.rollback()
            decision = RuleDecision(
                decision="rejected",
                rule="idempotency",
                summary="A refund has already been processed for this order.",
                detail="UNIQUE(order_id) violation on concurrent submit.",
            )
    else:
        await session.rollback()  # release row lock; nothing persisted

    await log_tool_call(
        customer_id=customer_id,
        tool_name="process_refund",
        arguments={"order_ref": order_ref, "reason": reason[:255]},
        result={**decision.model_dump(), **snapshot},
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )
    return RefundOutcome(decision, steps, snapshot)
