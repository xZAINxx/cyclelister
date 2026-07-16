"""Add listings.price_explanation (Phase 2 Smart Pricing, spec §6 step 8).

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("price_explanation", sa.Text))


def downgrade() -> None:
    op.drop_column("listings", "price_explanation")
