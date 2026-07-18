"""Add listings.stock_location (Phase 4 inventory; MotoLister gap adoption).

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("stock_location", sa.String(60)))


def downgrade() -> None:
    op.drop_column("listings", "stock_location")
