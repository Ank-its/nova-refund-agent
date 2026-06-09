"""Chat route: streams the tool-calling agent over dual-channel SSE.

One wire multiplexes channels via the ``event:`` field:
  meta -> conversation id + title · chat -> progress + final answer
  trace -> the agent's real tool calls/results (admin log) · control -> {done}

Recent history is replayed so multi-turn flows resume. With no LLM key, GRAPH is
None and a deterministic handler keeps the app demonstrable.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sse_starlette.sse import EventSourceResponse

from app.agent.fallback import regex_extract
from app.agent.graph import GRAPH
from app.agent.llm import compose_title
from app.agent.runtime import set_current_customer
from app.api.deps import current_principal
from app.api.security import Principal
from app.db.session import SessionLocal
from app.models.api import ChatRequest
from app.models.extraction import Intent
from app.services.conversations import (
    add_message,
    count_messages,
    create_conversation,
    get_conversation,
    get_messages,
)
from app.services.orders import list_orders
from app.services.refunds import process_refund

router = APIRouter(prefix="/api/chat", tags=["chat"])

_INJECTION_MARKERS = (
    "ignore all", "ignore previous", "ignore the rules", "disregard",
    "i am an admin", "i am an auditing", "force approve", "bypass",
    "override", "you must approve", "system prompt", "act as",
)

_TOOL_LABELS = {
    "get_refund_policy": "Checking the refund policy",
    "get_customer_orders": "Looking up your orders",
    "get_order_details": "Reviewing your order",
    "submit_refund": "Processing your refund",
}


def _looks_like_injection(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in _INJECTION_MARKERS)


def _sse(event: str, payload: dict) -> dict:
    return {"event": event, "data": json.dumps(payload)}


def _as_uuid(value: str | None) -> uuid.UUID | None:
    try:
        return uuid.UUID(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _to_messages(history: list[dict], user_text: str) -> list:
    """Replay stored turns as LangChain messages, then the new user message."""
    msgs: list = []
    for m in history:
        content = m.get("content") or ""
        if m.get("role") == "user":
            msgs.append(HumanMessage(content=content))
        elif m.get("role") == "assistant":
            msgs.append(AIMessage(content=content))
    msgs.append(HumanMessage(content=user_text))
    return msgs


def _parse_json(raw) -> dict | None:
    if isinstance(raw, dict):
        return raw
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {"value": val}
    except (TypeError, ValueError):
        return None


def _args_detail(args: dict) -> str:
    return " ".join(f"{k}={v}" for k, v in (args or {}).items() if k != "reason")[:200]


def _result_detail(name: str, result: dict | None) -> str:
    if not isinstance(result, dict):
        return ""
    if "decision" in result:
        return f"{result.get('decision')} ({result.get('rule')})"
    if "orders" in result:
        return f"{len(result['orders'])} order(s)"
    if "found" in result:
        return "order found" if result["found"] else "order not found"
    if "chars" in result:
        return "policy loaded"
    return ""


async def _emit_agent(state, request: Request, t0: float):
    """Stream the tool-calling graph. Yields SSE frames and finally a result dict.

    The trailing yielded value is a dict with the final answer + decision; the
    caller distinguishes it from SSE frames (which are dicts with an 'event' key).
    """
    seen = 0
    final_text = ""
    decision: dict = {}
    labels: list[str] = []
    guardrail_override: dict | None = None

    async for update in GRAPH.astream(state, stream_mode="values"):
        if await request.is_disconnected():
            break
        msgs = update["messages"]
        for msg in msgs[seen:]:
            if isinstance(msg, AIMessage):
                for tc in msg.tool_calls or []:
                    name = tc.get("name", "tool")
                    label = _TOOL_LABELS.get(name, name)
                    labels.append(label)
                    yield _sse("chat", {"role": "system", "type": "progress", "text": label})
                    yield _sse("trace", {
                        "type": "node", "node": name, "label": label,
                        "detail": _args_detail(tc.get("args", {})),
                        "data": tc.get("args", {}),
                        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                    })
                if msg.content and not msg.tool_calls:
                    final_text = msg.content if isinstance(msg.content, str) else str(msg.content)
            elif isinstance(msg, ToolMessage):
                name = msg.name or "tool"
                result = _parse_json(msg.content)
                yield _sse("trace", {
                    "type": "node", "node": f"{name}:result",
                    "label": f"{_TOOL_LABELS.get(name, name)} ✓",
                    "detail": _result_detail(name, result),
                    "data": result if isinstance(result, dict) else {},
                    "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                })
                if name == "submit_refund" and isinstance(result, dict):
                    decision = {
                        "decision": result.get("decision"),
                        "rule": result.get("rule"),
                        "summary": result.get("summary"),
                        "order": result.get("order") or {},
                    }
                    # guardrail catch: model recommended approve, policy blocked it
                    rec = (result.get("recommended_decision") or "").lower()
                    if result.get("recommendation_overridden") and rec == "approved" \
                            and result.get("decision") != "approved":
                        guardrail_override = result
            await asyncio.sleep(0)
        seen = len(msgs)

    yield {
        "final_text": final_text,
        "decision": decision,
        "labels": labels,
        "guardrail_override": guardrail_override,
    }


async def _emit_fallback(state_text: str, customer_id: uuid.UUID, t0: float):
    """No-LLM path: deterministic, single-shot, still policy-correct."""
    args = regex_extract(state_text)
    labels: list[str] = []
    decision: dict = {}

    if args.intent != Intent.request_refund and not args.order_ref:
        yield {
            "final_text": (
                "Hi! I'm Nova. I can help you return or refund an item — tell me "
                "what you'd like to return, or give an order reference like ORD_1001."
            ),
            "decision": {}, "labels": [], "guardrail_override": None,
        }
        return

    if not args.order_ref:
        async with SessionLocal() as s:
            orders = await list_orders(s, customer_id, None)
        listing = "\n".join(
            f"{i + 1}. {o.item_name} — ${float(o.amount):,.2f} ({o.order_ref})"
            for i, o in enumerate(orders)
        )
        labels = ["Looking up your orders"]
        yield _sse("trace", {"type": "node", "node": "get_customer_orders",
                             "label": "Looking up your orders", "detail": f"{len(orders)} order(s)",
                             "data": {}, "elapsed_ms": int((time.perf_counter() - t0) * 1000)})
        yield {
            "final_text": ("Which order is this about?\n\n" + listing) if orders
            else "I couldn't find any orders on your account.",
            "decision": {}, "labels": labels, "guardrail_override": None,
        }
        return

    labels = ["Processing your refund"]
    yield _sse("chat", {"role": "system", "type": "progress", "text": "Processing your refund"})
    async with SessionLocal() as s:
        outcome = await process_refund(
            s, customer_id=customer_id, order_ref=args.order_ref, reason=state_text
        )
    decision = {
        "decision": outcome.decision.decision, "rule": outcome.decision.rule,
        "summary": outcome.decision.summary, "order": outcome.order,
    }
    yield _sse("trace", {"type": "node", "node": "submit_refund",
                         "label": "Processing your refund ✓",
                         "detail": f"{outcome.decision.decision} ({outcome.decision.rule})",
                         "data": decision, "elapsed_ms": int((time.perf_counter() - t0) * 1000)})
    badge = {"approved": "✅ Approved", "pending_review": "🕒 Sent for human review",
             "rejected": "❌ Not eligible"}.get(outcome.decision.decision, "")
    yield {
        "final_text": f"{badge}\n\n{outcome.decision.summary}",
        "decision": decision, "labels": labels, "guardrail_override": None,
    }


async def _event_stream(principal: Principal, body: ChatRequest, request: Request):
    t0 = time.perf_counter()
    set_current_customer(principal.customer_id)

    async with SessionLocal() as s:
        conv = None
        conv_id_in = _as_uuid(body.conversation_id)
        if conv_id_in is not None:
            conv = await get_conversation(s, principal.user_id, conv_id_in)
        if conv is None:
            conv = await create_conversation(s, principal.user_id)
        conv_id = conv.id
        title = conv.title
        is_first = await count_messages(s, conv_id) == 0
        prior = await get_messages(s, conv_id)
        history = [{"role": m.role, "content": m.content} for m in prior][-10:]
        await add_message(s, conv_id, "user", body.message)
        await s.commit()

    yield _sse("meta", {"conversation_id": str(conv_id), "title": title})
    yield _sse("chat", {"role": "system", "type": "ack", "text": "Connected."})

    result: dict = {}
    try:
        if GRAPH is not None:
            state = {"messages": _to_messages(history, body.message)}
            gen = _emit_agent(state, request, t0)
        else:
            gen = _emit_fallback(body.message, principal.customer_id, t0)
        async for item in gen:
            if "event" in item:           # an SSE frame
                yield item
            else:                          # the trailing result dict
                result = item
    except Exception as exc:  # never leak a stack trace
        yield _sse("chat", {"role": "assistant", "type": "message",
                            "text": "Sorry, something went wrong handling that request."})
        yield _sse("trace", {"type": "error", "detail": str(exc)[:300]})
        yield _sse("control", {"type": "done"})
        return

    response = result.get("final_text") or "I'm not sure how to help with that."
    decision = result.get("decision") or {}
    labels = result.get("labels") or []
    steps = labels if labels else []  # empty for greetings (no tools called)

    yield _sse("chat", {
        "role": "assistant", "type": "message", "text": response,
        "decision": decision.get("decision"), "rule": decision.get("rule"),
        "candidates": [], "steps": steps,
    })

    if result.get("guardrail_override"):
        yield _sse("trace", {
            "type": "security_alert",
            "detail": "The agent recommended approval, but the policy engine "
                      "blocked it and applied the policy outcome instead.",
            "data": {"enforced": result["guardrail_override"].get("decision"),
                     "rule": result["guardrail_override"].get("rule")},
        })
    elif _looks_like_injection(body.message):
        yield _sse("trace", {
            "type": "security_alert",
            "detail": "Possible prompt-injection phrasing detected; treated as "
                      "literal text with no effect on the decision.",
            "data": {"sample": body.message[:160]},
        })

    new_title = title
    async with SessionLocal() as s:
        await add_message(
            s, conv_id, "assistant", response,
            decision=decision.get("decision"), rule=decision.get("rule"), steps=steps,
        )
        conv = await get_conversation(s, principal.user_id, conv_id)
        if conv is not None and is_first:
            new_title = await compose_title(body.message)
            conv.title = new_title
        await s.commit()

    if new_title != title:
        yield _sse("meta", {"conversation_id": str(conv_id), "title": new_title})

    yield _sse("trace", {
        "type": "summary", "total_ms": int((time.perf_counter() - t0) * 1000),
        "decision": decision.get("decision"), "rule": decision.get("rule"),
        "used_llm": GRAPH is not None,
    })
    yield _sse("control", {"type": "done"})


@router.post("")
async def chat(
    body: ChatRequest,
    request: Request,
    principal: Principal = Depends(current_principal),
) -> EventSourceResponse:
    if principal.customer_id is None:
        raise HTTPException(
            status_code=403,
            detail="This is an admin-only account. Chat is disabled; use the "
            "telemetry dashboard.",
        )
    return EventSourceResponse(_event_stream(principal, body, request))
