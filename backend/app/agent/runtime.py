"""Per-request agent context + the refund-policy loader.

The caller is pinned in a ContextVar rather than passed as a tool argument, so
the model can never name whose orders to read (an IDOR via prompt injection).
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar
from pathlib import Path

_current_customer: ContextVar[uuid.UUID | None] = ContextVar(
    "nova_current_customer", default=None
)


def set_current_customer(customer_id: uuid.UUID) -> None:
    _current_customer.set(customer_id)


def current_customer() -> uuid.UUID:
    cid = _current_customer.get()
    if cid is None:
        raise RuntimeError("No customer in context; set_current_customer() must run first.")
    return cid


_POLICY_PATH = Path(__file__).resolve().parent.parent / "data" / "refund_policy.txt"
_policy_cache: str | None = None


def load_policy() -> str:
    global _policy_cache
    if _policy_cache is None:
        _policy_cache = _POLICY_PATH.read_text(encoding="utf-8")
    return _policy_cache
