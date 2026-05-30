"""LangGraph state definition and small pure helpers."""
from __future__ import annotations

import operator
import re
from typing import Annotated, TypedDict

ORDER_RE = re.compile(r"ORD[_\- ]?(\d+)", re.IGNORECASE)


class AgentState(TypedDict, total=False):
    user_text: str
    customer_id: int
    history: list[dict]                 # prior turns: {role, content}
    pending_candidates: list[str]      # order refs offered last turn
    pending_reason_for: str | None     # order awaiting a return reason
    extracted: dict
    extractor: str                     # 'llm' | 'regex'
    decision: dict
    candidates: list[dict]
    order_snapshot: dict
    response: str
    used_llm: bool
    trace: Annotated[list[dict], operator.add]


def trace_event(node: str, label: str, detail: str = "", data: dict | None = None) -> dict:
    return {"node": node, "label": label, "detail": detail, "data": data or {}}


def extract_order_ref(text: str) -> str | None:
    """The ONLY source of an order ref: the customer's literal text.

    Never taken from the LLM output — a model can produce a well-formed but
    fabricated ref (e.g. invent one from a product name), which would skip the
    clarify loop and risk refunding the wrong order. A regex over raw input
    cannot invent a ref the user did not type.
    """
    m = ORDER_RE.search(text or "")
    return f"ORD_{m.group(1)}" if m else None


def resolve_selection(text: str, pending: list[str]) -> str | None:
    """Resolve a follow-up reply ('1' or 'ORD_1001') against offered candidates."""
    if not pending:
        return None
    m = ORDER_RE.search(text)
    if m:
        ref = f"ORD_{m.group(1)}"
        if ref in pending:
            return ref
    stripped = text.strip()
    if stripped.isdigit():
        idx = int(stripped) - 1
        if 0 <= idx < len(pending):
            return pending[idx]
    return None
