"""Domain enumerations shared across models, schemas, and services."""
from __future__ import annotations

ROLES = ("customer", "admin", "superuser")
LOYALTY_TIERS = ("standard", "silver", "gold", "platinum")
REFUND_STATUSES = ("approved", "rejected", "pending_review")
