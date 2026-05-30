"""conversations and messages

Revision ID: 0002_conversations
Revises: 0001_baseline
Create Date: 2026-05-30

Creates the chat-history tables. We build from the ORM metadata with
``create_all`` (checkfirst), so only the new tables are created and the
migration can never drift from the models.
"""
from alembic import op

from app.db.session import Base
import app.db.schema  # noqa: F401  (populate Base.metadata)

revision = "0002_conversations"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())  # checkfirst → only new tables


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("conversations")
