"""The refund rule matrix — a pure function with no I/O.

Because it has no database or LLM dependency, it is exhaustively unit-testable
and can never be influenced by prompt content. This is where — and the ONLY
where — a refund decision is made.
"""
from __future__ import annotations

from app.core.config import Settings
from app.models.decision import RuleDecision

# Predefined damage criteria: the only path by which an out-of-window request
# escalates to human review instead of being hard-rejected. Pure keyword match.
DAMAGE_KEYWORDS = (
    "damaged", "damage", "broken", "break", "defective", "defect", "faulty",
    "fault", "cracked", "shattered", "doa", "dead on arrival", "not working",
    "stopped working", "malfunction", "arrived broken", "spoiled", "leaking",
)


def reason_is_damage(reason: str) -> bool:
    low = (reason or "").lower()
    return any(kw in low for kw in DAMAGE_KEYWORDS)


def evaluate_rules(
    *,
    is_final_sale: bool,
    already_refunded: bool,
    days_since_purchase: int,
    amount: float,
    approved_refunds_30d: int,
    reason: str,
    settings: Settings,
) -> RuleDecision:
    """Evaluate the rigid rule matrix in fixed precedence (first match wins).

    1. Clearance guard   — final-sale items are structurally non-refundable
    2. Idempotency       — an order can only be refunded once
    3. Velocity          — serial-refund abuse is blocked
    4. Time window       — past window: damage -> escalate, else reject
    5. Financial limit   — over the high-value threshold -> human review
    6. Auto-approve
    """
    if is_final_sale:
        return RuleDecision(
            decision="rejected",
            rule="clearance_guard",
            summary="Item was a final clearance sale; final-sale items are never "
            "refundable and cannot be overridden.",
            detail="is_final_sale=True; structural block.",
        )

    if already_refunded:
        return RuleDecision(
            decision="rejected",
            rule="idempotency",
            summary="A refund has already been processed for this order, so it "
            "cannot be refunded again.",
            detail="existing refund row present.",
        )

    if approved_refunds_30d >= settings.velocity_limit:
        return RuleDecision(
            decision="rejected",
            rule="velocity",
            summary=f"The account has reached the limit of "
            f"{settings.velocity_limit} refunds within 30 days.",
            detail=f"approved_refunds_30d={approved_refunds_30d} >= "
            f"{settings.velocity_limit}.",
        )

    if days_since_purchase > settings.return_window_days:
        if reason_is_damage(reason):
            return RuleDecision(
                decision="pending_review",
                rule="time_window_damage_escalation",
                summary=f"Purchase is outside the "
                f"{settings.return_window_days}-day window, but the customer "
                "reported damage, so it is escalated to a human reviewer.",
                detail=f"days={days_since_purchase}; damage keyword matched.",
            )
        return RuleDecision(
            decision="rejected",
            rule="time_window",
            summary=f"Purchase is outside the "
            f"{settings.return_window_days}-day return window and the reason is "
            "not damage-related.",
            detail=f"days={days_since_purchase}; no damage reason.",
        )

    if float(amount) > settings.high_value_threshold:
        return RuleDecision(
            decision="pending_review",
            rule="high_value",
            summary=f"Order value exceeds ${settings.high_value_threshold:,.0f}, "
            "so it requires manual approval by the review team.",
            detail=f"amount={amount} > {settings.high_value_threshold}.",
        )

    return RuleDecision(
        decision="approved",
        rule="auto_approved",
        summary="All checks passed; the refund is approved and will be sent to "
        "the original payment method.",
        detail="all checks passed.",
    )
