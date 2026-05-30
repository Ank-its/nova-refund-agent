"""Read-side order queries — all parameterized and customer-scoped (IDOR guard)."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.schema import Order, utcnow


async def get_order(session: AsyncSession, customer_id: int, order_ref: str) -> Order | None:
    return await session.scalar(
        select(Order).where(
            Order.order_ref == order_ref, Order.customer_id == customer_id
        )
    )


async def list_orders(
    session: AsyncSession, customer_id: int, since: datetime | None
) -> list[Order]:
    q = select(Order).where(Order.customer_id == customer_id)
    if since is not None:
        q = q.where(Order.purchase_date >= since)
    return list((await session.scalars(q.order_by(Order.purchase_date.desc()))).all())


async def resolve_order_by_item(
    session: AsyncSession, customer_id: int, item_hint: str | None
) -> str | None:
    """Resolve a free-text product name to an order ref (Scenario 1).

    Returns the ref only on EXACTLY ONE match; zero or multiple matches return
    None so the caller falls back to the clarify loop instead of guessing.
    """
    if not item_hint or not item_hint.strip():
        return None
    rows = list(
        (
            await session.scalars(
                select(Order).where(
                    Order.customer_id == customer_id,
                    Order.item_name.ilike(f"%{item_hint.strip()}%"),
                )
            )
        ).all()
    )
    return rows[0].order_ref if len(rows) == 1 else None


async def find_candidate_orders(
    session: AsyncSession, customer_id: int
) -> tuple[str, list[Order]]:
    """Ambiguous-context fallback: this week -> this month -> full history."""
    week = await list_orders(session, customer_id, utcnow() - timedelta(days=7))
    if week:
        return "this week", week
    month = await list_orders(session, customer_id, utcnow() - timedelta(days=30))
    if month:
        return "this month", month
    return "your full history", await list_orders(session, customer_id, None)
