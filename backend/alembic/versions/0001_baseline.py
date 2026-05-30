"""baseline schema

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-30

Builds the full schema from the SQLAlchemy metadata so the migration can
never drift from the ORM models. CHECK constraints, the unique idempotency
constraint, and FK indexes are all defined on the models themselves.
"""
from alembic import op

from app.db.session import Base
import app.db.schema  # noqa: F401  (populate Base.metadata)

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
