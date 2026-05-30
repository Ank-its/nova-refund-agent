"""Outcome of the deterministic rule matrix."""
from __future__ import annotations

from pydantic import BaseModel


class RuleDecision(BaseModel):
    decision: str   # approved | rejected | pending_review
    rule: str       # machine code of the rule that fired
    summary: str    # short, factual basis for the decision (fed to the LLM writer)
    detail: str = ""  # internal detail for the audit log
