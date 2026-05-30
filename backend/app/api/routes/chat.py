"""Chat route with dual-channel SSE and DB-persisted history.

One SSE wire multiplexes channels via the ``event:`` field:
  event: meta    -> conversation id + (live-updated) title for the sidebar
  event: chat    -> customer-facing (transient progress + final answer)
  event: trace   -> structural LangGraph telemetry (nodes, args, latency, alerts)
  event: control -> {done}

Every user and assistant turn is persisted. Multi-turn agent state (the order
awaiting a reason, offered candidates) lives on the conversation row, and recent
history is replayed into the agent so follow-ups are answered in context.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.agent.graph import GRAPH
from app.agent.llm import compose_title
from app.agent.state import AgentState
from app.api.deps import current_principal
from app.api.security import Principal
from app.db.session import SessionLocal
from app.models.api import ChatRequest
from app.services.conversations import (
    add_message,
    count_messages,
    create_conversation,
    get_conversation,
    get_messages,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])

_INJECTION_MARKERS = (
    "ignore all", "ignore previous", "ignore the rules", "disregard",
    "i am an admin", "i am an auditing", "force approve", "bypass",
    "override", "you must approve", "system prompt", "act as",
)


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


async def _event_stream(principal: Principal, body: ChatRequest, request: Request):
    t0 = time.perf_counter()

    # --- Load or create the conversation; capture state + history ---
    async with SessionLocal() as s:
        conv = None
        conv_id_in = _as_uuid(body.conversation_id)
        if conv_id_in is not None:
            conv = await get_conversation(s, principal.user_id, conv_id_in)
        if conv is None:
            conv = await create_conversation(s, principal.user_id)
        conv_id = conv.id
        title = conv.title
        pending_ref = conv.pending_order_ref
        pending_cands = list(conv.pending_candidates or [])
        is_first = await count_messages(s, conv_id) == 0

        prior = await get_messages(s, conv_id)
        history = [{"role": m.role, "content": m.content} for m in prior][-10:]

        await add_message(s, conv_id, "user", body.message)
        await s.commit()

    yield _sse("meta", {"conversation_id": str(conv_id), "title": title})
    yield _sse("chat", {"role": "system", "type": "ack", "text": "Connected."})

    state: AgentState = {
        "user_text": body.message,
        "customer_id": principal.customer_id,
        "history": history,
        "pending_candidates": pending_cands,
        "pending_reason_for": pending_ref,
        "trace": [],
    }

    final: AgentState = {}
    emitted = 0
    try:
        async for update in GRAPH.astream(state, stream_mode="values"):
            if await request.is_disconnected():
                break
            final = update
            for step in update.get("trace", [])[emitted:]:
                yield _sse("chat", {"role": "system", "type": "progress", "text": step["label"]})
                yield _sse("trace", {
                    "type": "node",
                    "node": step["node"],
                    "label": step["label"],
                    "detail": step["detail"],
                    "data": step["data"],
                    "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                })
                await asyncio.sleep(0)
            emitted = len(update.get("trace", []))
    except Exception as exc:  # never leak a stack trace
        yield _sse("chat", {"role": "assistant", "type": "message",
                            "text": "Sorry, something went wrong handling that request."})
        yield _sse("trace", {"type": "error", "detail": str(exc)[:300]})
        yield _sse("control", {"type": "done"})
        return

    response = final.get("response", "I'm not sure how to help with that.")
    decision = final.get("decision") or {}
    candidates = final.get("candidates") or []
    steps = [t["label"] for t in final.get("trace", [])]

    yield _sse("chat", {
        "role": "assistant",
        "type": "message",
        "text": response,
        "decision": decision.get("decision"),
        "rule": decision.get("rule"),
        "candidates": candidates,
    })

    if _looks_like_injection(body.message):
        yield _sse("trace", {
            "type": "security_alert",
            "detail": "Possible prompt-injection phrasing detected; neutralized "
                      "as literal text (no effect on the decision).",
            "data": {"sample": body.message[:160]},
        })

    # --- Persist assistant turn + updated agent state; title the first turn ---
    new_title = title
    async with SessionLocal() as s:
        await add_message(
            s, conv_id, "assistant", response,
            decision=decision.get("decision"),
            rule=decision.get("rule"),
            steps=steps,
        )
        conv = await get_conversation(s, principal.user_id, conv_id)
        if conv is not None:
            conv.pending_order_ref = final.get("pending_reason_for")
            conv.pending_candidates = [c["order_ref"] for c in candidates]
            if is_first:
                new_title = await compose_title(body.message)
                conv.title = new_title
        await s.commit()

    if new_title != title:
        yield _sse("meta", {"conversation_id": str(conv_id), "title": new_title})

    yield _sse("trace", {
        "type": "summary",
        "total_ms": int((time.perf_counter() - t0) * 1000),
        "decision": decision.get("decision"),
        "rule": decision.get("rule"),
        "used_llm": final.get("used_llm", False),
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
