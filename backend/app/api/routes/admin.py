"""Admin telemetry routes — backing data for the right-hand dashboard."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, require_admin
from app.db.session import get_db
from app.db.schema import Refund, ToolAuditLog

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/telemetry")
async def telemetry(
    _: Principal = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> dict:
    total_calls = await db.scalar(select(func.count(ToolAuditLog.id))) or 0
    avg_latency = await db.scalar(select(func.avg(ToolAuditLog.latency_ms))) or 0

    by_status_rows = (
        await db.execute(
            select(Refund.status, func.count(Refund.id)).group_by(Refund.status)
        )
    ).all()

    recent_rows = (
        await db.scalars(
            select(ToolAuditLog).order_by(desc(ToolAuditLog.created_at)).limit(25)
        )
    ).all()

    return {
        "totals": {
            "tool_calls": total_calls,
            "avg_latency_ms": round(float(avg_latency), 1),
            "refunds_by_status": {s: c for s, c in by_status_rows},
        },
        "recent_calls": [
            {
                "id": str(r.id),
                "tool": r.tool_name,
                "arguments": r.arguments,
                "result": r.result,
                "latency_ms": r.latency_ms,
                "created_at": r.created_at.isoformat(),
            }
            for r in recent_rows
        ],
    }
