"""Tool-call audit logging (own session, decoupled from the refund txn)."""
from __future__ import annotations

from app.db.session import SessionLocal
from app.db.schema import ToolAuditLog


async def log_tool_call(
    *,
    customer_id: int | None,
    tool_name: str,
    arguments: dict,
    result: dict,
    latency_ms: int,
) -> None:
    async with SessionLocal() as session:
        session.add(
            ToolAuditLog(
                customer_id=customer_id,
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                latency_ms=latency_ms,
            )
        )
        await session.commit()
