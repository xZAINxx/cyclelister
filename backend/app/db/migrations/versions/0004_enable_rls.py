"""Enable RLS (deny-all) on every table — closes Supabase's PostgREST surface.

The FastAPI backend connects as the table-owning postgres role, which bypasses
RLS, so the app is unaffected. With RLS on and no policies, the anon/
authenticated REST roles can neither read nor write anything (spec §15,
least privilege). Fixes Supabase advisor `rls_disabled_in_public` (CRITICAL).

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-20
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TABLES = (
    "users",
    "parts",
    "fitment",
    "listings",
    "listing_images",
    "sales_history",
    "pricing_rules",
    "templates",
    "jobs",
    "ebay_tokens",
    "alembic_version",
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return  # RLS is a Postgres feature; dev SQLite has no REST surface
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
