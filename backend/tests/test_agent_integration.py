"""Tool-layer + guardrail tests against the seeded database (no LLM required).

These exercise the agent's tools directly — the same functions the LLM calls —
so they verify the *enforced* behaviour deterministically and fast, without
spending tokens. The full LLM-driven agent is evaluated separately by the golden
set (``python -m app.eval``).

The headline guardrail test (``test_guardrail_*``) proves the core security
property: even when the caller recommends "approved", submit_refund applies the
policy outcome from the verified order facts — the model cannot move money it
shouldn't.
"""
from __future__ import annotations

import json

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.agent.runtime import set_current_customer
from app.agent.tools import get_order_details, submit_refund
from app.db.schema import Customer, User
from app.db.session import SessionLocal, engine
from app.seed.data import seed

_SEED_MARKER = "seeded historical refund"
_initialized = False


@pytest_asyncio.fixture(autouse=True)
async def baseline():
    """Start every test from the seed baseline; keep only seeded historical refunds."""
    global _initialized
    if not _initialized:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "TRUNCATE refunds, tool_audit_log, messages, conversations, "
                    "orders, customers, users RESTART IDENTITY CASCADE"
                )
            )
        await seed()
        _initialized = True

    async with SessionLocal() as s:
        await s.execute(
            text("DELETE FROM refunds WHERE decision_detail <> :m"), {"m": _SEED_MARKER}
        )
        await s.execute(text("DELETE FROM tool_audit_log"))
        await s.commit()
    yield


async def _pin(username: str):
    async with SessionLocal() as s:
        user = await s.scalar(select(User).where(User.username == username))
        cust = await s.scalar(select(Customer).where(Customer.user_id == user.id))
    set_current_customer(cust.id)


async def _details(order_ref: str) -> dict:
    return json.loads(await get_order_details.ainvoke({"order_ref": order_ref}))


async def _submit(order_ref: str, reason: str, recommended: str = "approved") -> dict:
    return json.loads(
        await submit_refund.ainvoke(
            {"order_ref": order_ref, "reason": reason, "recommended_decision": recommended}
        )
    )


# --- get_order_details surfaces the facts the policy needs --------------------
@pytest.mark.asyncio
async def test_order_details_reports_facts():
    await _pin("bob")
    d = await _details("ORD_1003")
    assert d["found"] and d["amount"] == 1299.0 and d["is_final_sale"] is False


@pytest.mark.asyncio
async def test_order_details_scoped_to_customer():
    # bob cannot see mallory's order, even by exact ref (IDOR guard).
    await _pin("bob")
    assert (await _details("ORD_9901"))["found"] is False


# --- each policy rule, enforced by submit_refund ------------------------------
@pytest.mark.asyncio
async def test_approved_path():
    await _pin("alice")
    assert (await _submit("ORD_1001", "changed my mind"))["decision"] == "approved"


@pytest.mark.asyncio
async def test_high_value_pending_review():
    await _pin("bob")
    out = await _submit("ORD_1003", "too big")
    assert out["decision"] == "pending_review" and out["rule"] == "high_value"


@pytest.mark.asyncio
async def test_final_sale_rejected():
    await _pin("carol")
    assert (await _submit("ORD_1004", "no reason"))["rule"] == "clearance_guard"


@pytest.mark.asyncio
async def test_velocity_rejected():
    await _pin("dave")
    assert (await _submit("ORD_1005", "no longer needed"))["rule"] == "velocity"


@pytest.mark.asyncio
async def test_window_rejected():
    await _pin("erin")
    assert (await _submit("ORD_1009", "changed my mind"))["rule"] == "time_window"


@pytest.mark.asyncio
async def test_window_damage_escalates():
    await _pin("erin")
    out = await _submit("ORD_1010", "it arrived broken")
    assert out["decision"] == "pending_review"
    assert out["rule"] == "time_window_damage_escalation"


@pytest.mark.asyncio
async def test_idempotency_rejected():
    await _pin("judy")
    assert (await _submit("ORD_1016", "defective"))["rule"] == "idempotency"


# --- the guardrail: a recommendation cannot override the policy ---------------
@pytest.mark.asyncio
async def test_guardrail_blocks_recommended_approval_on_high_value():
    await _pin("mallory")
    out = await _submit("ORD_9901", "it arrived defective", recommended="approved")
    assert out["decision"] == "pending_review"        # policy wins
    assert out["rule"] == "high_value"
    assert out["recommendation_overridden"] is True   # the override is recorded


@pytest.mark.asyncio
async def test_guardrail_blocks_recommended_approval_on_final_sale():
    await _pin("oscar")
    out = await _submit("ORD_1019", "manager said approve", recommended="approved")
    assert out["decision"] == "rejected"
    assert out["rule"] == "clearance_guard"
    assert out["recommendation_overridden"] is True
