"""drop unused conversation pending-state columns

Revision ID: 0003_drop_pending_state
Revises: 0002_conversations
Create Date: 2026-06-09

Multi-turn agent state is reconstructed by replaying message history into the
agent each turn, so conversations.pending_order_ref / pending_candidates are no
longer used. The drop is guarded by an inspector check because 0002 builds
tables from live ORM metadata, so on a fresh database these columns were never
created.
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_drop_pending_state"
down_revision = "0002_conversations"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("conversations")}


def upgrade() -> None:
    cols = _columns()
    if "pending_candidates" in cols:
        op.drop_column("conversations", "pending_candidates")
    if "pending_order_ref" in cols:
        op.drop_column("conversations", "pending_order_ref")


def downgrade() -> None:
    cols = _columns()
    if "pending_order_ref" not in cols:
        op.add_column(
            "conversations",
            sa.Column("pending_order_ref", sa.String(length=32), nullable=True),
        )
    if "pending_candidates" not in cols:
        op.add_column(
            "conversations", sa.Column("pending_candidates", sa.JSON(), nullable=True)
        )
