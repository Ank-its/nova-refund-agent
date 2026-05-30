"""LangGraph nodes.

Conversation shape (a reason is collected before any refund is processed):

    extract -(route)-> ask_reason -> END      (order identified -> ask why)
                  |--> decide      -> END      (reason supplied -> evaluate)
                  |--> clarify     -> END      (no order -> offer choices)
                  +--> smalltalk   -> END      (no actionable request)

The LLM is confined to extraction + reply phrasing; every refund decision is
made by the deterministic rule service.
"""
from __future__ import annotations

from app.agent.llm import compose_greeting, compose_reply, extract_args
from app.agent.state import (
    AgentState,
    extract_order_ref,
    resolve_selection,
    trace_event,
)
from app.db.session import SessionLocal
from app.models.extraction import Intent
from app.services.orders import (
    find_candidate_orders,
    get_order,
    list_orders,
    resolve_order_by_item,
)
from app.services.refunds import process_refund


def _order_dict(o) -> dict:
    return {
        "order_ref": o.order_ref,
        "item_name": o.item_name,
        "amount": float(o.amount),
        "purchase_date": o.purchase_date.isoformat(),
    }


def _format_orders(orders: list[dict]) -> str:
    return "\n".join(
        f"{i + 1}. {c['item_name']} -- ${c['amount']:,.2f} ({c['order_ref']})"
        for i, c in enumerate(orders)
    )


async def extract(state: AgentState) -> dict:
    text = state["user_text"]
    pending = state.get("pending_candidates") or []
    args, extractor = await extract_args(text)

    # Air-gap: the order ref comes ONLY from the literal text, never the LLM.
    args.order_ref = extract_order_ref(text)

    # A named product with no code -> resolve against the customer's history.
    if not args.order_ref and args.item_hint:
        async with SessionLocal() as session:
            resolved = await resolve_order_by_item(
                session, state["customer_id"], args.item_hint
            )
        if resolved:
            args.order_ref = resolved

    # Follow-up selection from a prior clarification turn.
    if not args.order_ref:
        selected = resolve_selection(text, pending)
        if selected:
            args.order_ref = selected
            if args.intent == Intent.other:
                args.intent = Intent.request_refund

    return {
        "extracted": args.model_dump(),
        "extractor": extractor,
        "used_llm": extractor == "llm",
        "trace": [
            trace_event(
                "extract",
                "Understanding your request",
                f"intent={args.intent.value} order_ref={args.order_ref} "
                f"item_hint={args.item_hint} (reason is inert literal text)",
                {"extracted": args.model_dump(), "extractor": extractor},
            )
        ],
    }


def route(state: AgentState) -> str:
    # If we asked for a reason last turn, this message IS the reason -> decide.
    if state.get("pending_reason_for"):
        return "decide"
    ex = state["extracted"]
    if ex["order_ref"]:
        return "ask_reason"
    if ex["intent"] == Intent.request_refund.value:
        return "clarify"
    return "smalltalk"


async def ask_reason(state: AgentState) -> dict:
    """Order identified -- confirm it and ask for the return reason."""
    ref = state["extracted"]["order_ref"]
    async with SessionLocal() as session:
        order = await get_order(session, state["customer_id"], ref)

    if order is None:
        return {
            "pending_reason_for": None,
            "candidates": [],
            "response": (
                "I couldn't find that order on your account. Could you "
                "double-check the order reference?"
            ),
            "trace": [
                trace_event("ask_reason", "Locating your order",
                            f"order_ref={ref} not found")
            ],
        }

    response = (
        f"Got it -- you'd like to return your {order.item_name} ({ref}). "
        "Before I process this, could you tell me the reason for the return?"
    )
    return {
        "pending_reason_for": ref,
        "candidates": [],
        "response": response,
        "trace": [
            trace_event(
                "ask_reason",
                "Asking for the return reason",
                f"order_ref={ref}; awaiting reason",
                {"order_ref": ref, "item": order.item_name},
            )
        ],
    }


async def decide(state: AgentState) -> dict:
    if state.get("pending_reason_for"):
        order_ref = state["pending_reason_for"]
        reason = (state["user_text"] or "").strip()
    else:
        ex = state["extracted"]
        order_ref = ex["order_ref"]
        reason = ex.get("reason", "")

    async with SessionLocal() as session:
        outcome = await process_refund(
            session,
            customer_id=state["customer_id"],
            order_ref=order_ref,
            reason=reason,
        )

    trace = [trace_event("decide", s.label, s.detail, s.data) for s in outcome.steps]
    trace.append(
        trace_event(
            "decide",
            "Decision ready",
            f"rule={outcome.decision.rule} -> {outcome.decision.decision}",
            {"decision": outcome.decision.model_dump(), "order": outcome.order},
        )
    )

    reply = await compose_reply(
        decision=outcome.decision.decision,
        summary=outcome.decision.summary,
        order=outcome.order,
        reason=reason,
    )

    return {
        "decision": {**outcome.decision.model_dump(), "order": outcome.order},
        "order_snapshot": outcome.order,
        "response": reply,
        "pending_reason_for": None,  # reason consumed; clear the gate
        "trace": trace,
    }


async def clarify(state: AgentState) -> dict:
    """No specific order yet. If the customer named an item, search their FULL
    history for it; acknowledge when it isn't found instead of dumping a
    generic list. Otherwise offer recent orders to choose from.
    """
    customer_id = state["customer_id"]
    item_hint = (state.get("extracted") or {}).get("item_hint")

    async with SessionLocal() as session:
        all_orders = await list_orders(session, customer_id, None)
        window, recent = await find_candidate_orders(session, customer_id)
        recent_dicts = [_order_dict(o) for o in recent]

        matched: list[dict] = []
        if item_hint:
            needle = item_hint.strip().lower()
            matched = [
                _order_dict(o) for o in all_orders if needle in o.item_name.lower()
            ]

    # No orders at all on the account.
    if not all_orders:
        return {
            "candidates": [],
            "response": (
                "I couldn't find any orders on your account, so there's nothing "
                "to return. If you think this is a mistake, please contact support."
            ),
            "trace": [trace_event("clarify", "Finding your orders", "no orders")],
        }

    # Customer named an item but nothing in their history matches it.
    if item_hint and not matched:
        response = (
            f"I couldn't find anything matching \"{item_hint}\" in your orders. "
            "Here's what's on your account"
            f"{' from ' + window if recent_dicts else ''}:\n\n"
            f"{_format_orders(recent_dicts)}\n\n"
            "Reply with the number or the order reference, or tell me a "
            "different item."
        )
        return {
            "candidates": recent_dicts,
            "response": response,
            "trace": [
                trace_event(
                    "clarify",
                    "Item not found",
                    f"item_hint={item_hint!r} matched 0 orders",
                    {"item_hint": item_hint, "offered": len(recent_dicts)},
                )
            ],
        }

    # Named item matched more than one order -> let them pick among the matches.
    if matched and len(matched) > 1:
        response = (
            f"I found a few orders matching \"{item_hint}\":\n\n"
            f"{_format_orders(matched)}\n\n"
            "Which one would you like to return? Reply with the number or "
            "order reference."
        )
        return {
            "candidates": matched,
            "response": response,
            "trace": [
                trace_event(
                    "clarify",
                    "Multiple item matches",
                    f"item_hint={item_hint!r} matched {len(matched)}",
                    {"item_hint": item_hint, "count": len(matched)},
                )
            ],
        }

    # No item named -> general "which order?" using recent orders.
    response = (
        f"Which order is this about? Here are your orders from {window}:\n\n"
        f"{_format_orders(recent_dicts)}\n\n"
        "Reply with the number or the order reference."
    )
    return {
        "candidates": recent_dicts,
        "response": response,
        "trace": [
            trace_event(
                "clarify",
                "Finding your recent orders",
                f"window={window}; {len(recent_dicts)} candidate(s)",
                {"window": window, "count": len(recent_dicts)},
            )
        ],
    }


async def smalltalk(state: AgentState) -> dict:
    # Pass recent history so follow-ups ("any updates?") are answered in
    # context (e.g. referencing a refund that is pending review), not as a
    # generic greeting.
    response = await compose_greeting(state["user_text"], state.get("history") or [])
    return {
        "response": response,
        "trace": [trace_event("smalltalk", "Replying", "no new refund action")],
    }
