"""The agent's tools — the capabilities the LLM invokes.

Two invariants are enforced here, in code, not by trusting the model:
  - Customer scoping: every query is bound to current_customer() (IDOR guard).
  - Decision authority: submit_refund recomputes the outcome from the rule engine
    over verified facts and persists THAT, not the model's recommendation.
Every call is written to the tool-audit log behind the admin dashboard.
"""
from __future__ import annotations

import json
import time
from datetime import timedelta

from langchain_core.tools import tool
from sqlalchemy import func, select

from app.agent.runtime import current_customer, load_policy
from app.core.config import get_settings
from app.db.schema import Order, Refund, utcnow
from app.db.session import SessionLocal
from app.services.audit import log_tool_call
from app.services.refunds import process_refund


async def _audit(tool_name: str, arguments: dict, result: dict, t0: float) -> None:
    await log_tool_call(
        customer_id=current_customer(),
        tool_name=tool_name,
        arguments=arguments,
        result=result,
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )


@tool
async def get_refund_policy() -> str:
    """Return the full corporate Refund Policy document.

    Call this before deciding any refund so your reasoning is grounded in the
    current written policy (rules, precedence, and the damage exception).
    """
    t0 = time.perf_counter()
    policy = load_policy()
    await _audit("get_refund_policy", {}, {"chars": len(policy)}, t0)
    return policy


@tool
async def get_customer_orders() -> str:
    """List the current customer's orders, most recent first (JSON).

    Use this to find which order a customer means when they don't give an order
    reference, or to disambiguate when they only describe an item by name.
    """
    t0 = time.perf_counter()
    cid = current_customer()
    async with SessionLocal() as s:
        rows = list(
            (
                await s.scalars(
                    select(Order)
                    .where(Order.customer_id == cid)
                    .order_by(Order.purchase_date.desc())
                )
            ).all()
        )
    orders = [
        {
            "order_ref": o.order_ref,
            "item_name": o.item_name,
            "amount": float(o.amount),
            "purchase_date": o.purchase_date.date().isoformat(),
            "is_final_sale": o.is_final_sale,
        }
        for o in rows
    ]
    await _audit("get_customer_orders", {}, {"count": len(orders)}, t0)
    return json.dumps({"orders": orders})


@tool
async def get_order_details(order_ref: str) -> str:
    """Return the verified facts for ONE order, needed to apply the policy (JSON).

    Includes amount, days since purchase, final-sale flag, whether it has already
    been refunded, and the customer's approved-refund count in the trailing 30
    days. Call this before submitting a refund so you reason over real facts.
    """
    t0 = time.perf_counter()
    cid = current_customer()
    settings = get_settings()
    async with SessionLocal() as s:
        order = await s.scalar(
            select(Order).where(
                Order.order_ref == order_ref, Order.customer_id == cid
            )
        )
        if order is None:
            result = {"found": False, "order_ref": order_ref}
            await _audit("get_order_details", {"order_ref": order_ref}, result, t0)
            return json.dumps(result)

        already_refunded = (
            await s.scalar(select(Refund).where(Refund.order_id == order.id))
        ) is not None
        approved_30d = (
            await s.scalar(
                select(func.count(Refund.id)).where(
                    Refund.customer_id == cid,
                    Refund.status == "approved",
                    Refund.created_at
                    >= utcnow() - timedelta(days=settings.velocity_window_days),
                )
            )
            or 0
        )
        result = {
            "found": True,
            "order_ref": order.order_ref,
            "item_name": order.item_name,
            "amount": float(order.amount),
            "days_since_purchase": (utcnow() - order.purchase_date).days,
            "is_final_sale": order.is_final_sale,
            "already_refunded": already_refunded,
            "approved_refunds_last_30d": approved_30d,
        }
    await _audit("get_order_details", {"order_ref": order_ref}, result, t0)
    return json.dumps(result)


@tool
async def submit_refund(order_ref: str, reason: str, recommended_decision: str) -> str:
    """Submit a refund for processing and return the AUTHORITATIVE outcome (JSON).

    Call this only once you know the order and the customer's reason. Pass your
    own policy-based recommendation in ``recommended_decision`` (one of
    "approved", "rejected", "pending_review").

    The decision the system actually applies is recomputed from the deterministic
    policy engine over the verified order facts and returned to you — it may
    differ from your recommendation. Phrase your reply from the RETURNED
    decision, never from your recommendation, and never promise an outcome for a
    "pending_review" (human-reviewed) case.
    """
    t0 = time.perf_counter()
    cid = current_customer()
    async with SessionLocal() as s:
        outcome = await process_refund(
            s, customer_id=cid, order_ref=order_ref, reason=reason
        )

    authoritative = outcome.decision.decision
    overridden = (
        recommended_decision or ""
    ).strip().lower() != authoritative and recommended_decision is not None
    result = {
        "decision": authoritative,
        "rule": outcome.decision.rule,
        "summary": outcome.decision.summary,
        "order": outcome.order,
        "recommended_decision": recommended_decision,
        "recommendation_overridden": overridden,
    }
    await _audit(
        "submit_refund",
        {"order_ref": order_ref, "reason": reason[:255],
         "recommended_decision": recommended_decision},
        result,
        t0,
    )
    return json.dumps(result)


# All tools the agent may call, in a stable order.
TOOLS = [get_refund_policy, get_customer_orders, get_order_details, submit_refund]
