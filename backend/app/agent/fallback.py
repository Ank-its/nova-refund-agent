"""Deterministic, no-API-key fallbacks for extraction and reply writing.

These guarantee the system is fully demonstrable without an LLM, and the rule
engine produces identical decisions whether the LLM or these run.
"""
from __future__ import annotations

import re

from app.models.extraction import ExtractedArgs, Intent

ORDER_RE = re.compile(r"ORD[_\- ]?(\d+)", re.IGNORECASE)
REFUND_WORDS = ("refund", "return", "money back", "send back", "give back")

# A small product lexicon lets the regex extractor populate item_hint so that
# item-name resolution (Scenario 1) works even without an LLM.
_PRODUCT_WORDS = (
    "headphones", "cable", "tv", "speaker", "charger", "sleeve", "webcam",
    "chair", "desk", "planner", "lamp", "mouse", "keyboard", "bottle",
    "case", "laptop", "vase", "mug", "monitor", "stand", "jacket",
)


def _guess_item_hint(text: str) -> str | None:
    low = text.lower()
    hits = [w for w in _PRODUCT_WORDS if w in low]
    if not hits:
        return None
    # Prefer a two-word phrase like "monitor stand" when both words appear.
    for a, b in (("monitor", "stand"), ("laptop", "sleeve"), ("phone", "case")):
        if a in low and b in low:
            return f"{a} {b}"
    return hits[0]


def regex_extract(text: str) -> ExtractedArgs:
    low = text.lower()
    m = ORDER_RE.search(text)
    order_ref = f"ORD_{m.group(1)}" if m else None
    wants_refund = bool(order_ref) or any(w in low for w in REFUND_WORDS)
    return ExtractedArgs(
        intent=Intent.request_refund if wants_refund else Intent.other,
        order_ref=order_ref,
        item_hint=None if order_ref else _guess_item_hint(text),
        # The entire message becomes literal reason text — never instructions.
        reason=text.strip()[:255],
    )


_BADGE = {
    "approved": "✅ Approved",
    "pending_review": "🕒 Sent for human review",
    "rejected": "❌ Not eligible",
}


def template_reply(*, decision: str, summary: str, order: dict) -> str:
    """Clean, factual reply used when no LLM is configured."""
    parts = [_BADGE.get(decision, decision), "", summary]
    if order:
        parts.append("")
        parts.append(
            f"Order {order['order_ref']} — {order['item_name']} "
            f"(${order['amount']:,.2f})"
        )
    return "\n".join(parts)
