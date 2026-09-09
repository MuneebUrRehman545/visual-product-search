"""Add step timestamps

Revision ID: 002
Revises: 001
Create Date: 2026-08-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("steps", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("steps", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("steps", "completed_at")
    op.drop_column("steps", "started_at")
