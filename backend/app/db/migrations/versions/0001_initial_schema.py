"""Initial schema — spec §5 tables plus ebay_tokens.

Revision ID: 0001
Revises:
Create Date: 2026-07-12
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _base_columns():
    return [
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        *_base_columns(),
        sa.Column("email", sa.String(320)),
        sa.Column("display_name", sa.String(200)),
        sa.Column("role", sa.String(20), nullable=False, server_default="owner"),
        sa.Column("supabase_sub", sa.String(64), unique=True),
    )
    op.create_index("ix_users_supabase_sub", "users", ["supabase_sub"])

    op.create_table(
        "parts",
        *_base_columns(),
        sa.Column("part_number", sa.String(64), nullable=False),
        sa.Column("part_number_display", sa.String(64)),
        sa.Column("brand", sa.String(64)),
        sa.Column("part_type", sa.String(120)),
        sa.Column("title_template", sa.String(120)),
        sa.Column("description_template", sa.Text),
        sa.Column("default_category_id", sa.String(32)),
        sa.Column("item_specifics", postgresql.JSONB),
        sa.Column("notes", sa.Text),
        sa.Column("source", sa.String(20), nullable=False, server_default="ai_generated"),
    )
    op.create_index("ix_parts_part_number", "parts", ["part_number"])

    op.create_table(
        "fitment",
        *_base_columns(),
        sa.Column("part_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("parts.id"), nullable=False),
        sa.Column("make", sa.String(64), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("year_start", sa.Integer),
        sa.Column("year_end", sa.Integer),
        sa.Column("confidence", sa.Numeric(3, 2)),
        sa.Column("confirmed", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_fitment_part_id", "fitment", ["part_id"])

    op.create_table(
        "listings",
        *_base_columns(),
        sa.Column("part_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("parts.id")),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("ebay_listing_id", sa.String(40)),
        sa.Column("title", sa.String(80)),
        sa.Column("description", sa.Text),
        sa.Column("price", sa.Numeric(10, 2)),
        sa.Column("price_floor", sa.Numeric(10, 2)),
        sa.Column("computed_competitor_price", sa.Numeric(10, 2)),
        sa.Column("undercut_pct", sa.Numeric(4, 2)),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("category_id", sa.String(32)),
        sa.Column("item_specifics", postgresql.JSONB),
        sa.Column("shipping_policy_id", sa.String(40)),
        sa.Column("return_policy_id", sa.String(40)),
        sa.Column("payment_policy_id", sa.String(40)),
        sa.Column("condition", sa.String(60)),
        sa.Column("condition_notes", sa.Text),
        sa.Column("ai_confidence", sa.Numeric(3, 2)),
        sa.Column("needs_human_review", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("price_source", sa.String(40)),
        sa.Column("hint", sa.String(200)),
    )
    op.create_index("ix_listings_status", "listings", ["status"])
    op.create_index("ix_listings_part_id", "listings", ["part_id"])

    op.create_table(
        "listing_images",
        *_base_columns(),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("listings.id"), nullable=False),
        sa.Column("part_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("parts.id")),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False, server_default="image/jpeg"),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("order_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("processed_path", sa.String(500)),
    )
    op.create_index("ix_listing_images_listing_id", "listing_images", ["listing_id"])
    op.create_index("ix_listing_images_part_id", "listing_images", ["part_id"])

    op.create_table(
        "sales_history",
        *_base_columns(),
        sa.Column("part_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("parts.id")),
        sa.Column("original_listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("listings.id")),
        sa.Column("part_number", sa.String(64)),
        sa.Column("title", sa.String(80)),
        sa.Column("description", sa.Text),
        sa.Column("sold_price", sa.Numeric(10, 2)),
        sa.Column("sold_date", sa.DateTime(timezone=True)),
        sa.Column("image_paths", postgresql.JSONB),
        sa.Column("buyer_ref", sa.String(120)),
        sa.Column("fitment_snapshot", postgresql.JSONB),
    )
    op.create_index("ix_sales_history_part_id", "sales_history", ["part_id"])
    op.create_index("ix_sales_history_part_number", "sales_history", ["part_number"])

    op.create_table(
        "pricing_rules",
        *_base_columns(),
        sa.Column("scope", sa.String(20), nullable=False, server_default="global"),
        sa.Column("scope_ref", sa.String(64)),
        sa.Column("undercut_pct_min", sa.Numeric(4, 2), nullable=False, server_default="5"),
        sa.Column("undercut_pct_max", sa.Numeric(4, 2), nullable=False, server_default="10"),
        sa.Column("price_ending", sa.String(8), nullable=False, server_default=".95"),
        sa.Column("floor_absolute", sa.Numeric(10, 2)),
        sa.Column("floor_margin_pct", sa.Numeric(5, 2)),
        sa.Column("free_shipping_threshold", sa.Numeric(10, 2)),
    )

    op.create_table(
        "templates",
        *_base_columns(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("part_type", sa.String(120)),
        sa.Column("shipping_policy_id", sa.String(40)),
        sa.Column("return_policy_id", sa.String(40)),
        sa.Column("payment_policy_id", sa.String(40)),
        sa.Column("description_boilerplate", sa.Text),
        sa.Column("item_specifics_defaults", postgresql.JSONB),
    )

    op.create_table(
        "jobs",
        *_base_columns(),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("payload", postgresql.JSONB),
        sa.Column("result", postgresql.JSONB),
        sa.Column("error", sa.Text),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"])

    op.create_table(
        "ebay_tokens",
        *_base_columns(),
        sa.Column("environment", sa.String(20), nullable=False, unique=True),
        sa.Column("access_token_enc", sa.Text, nullable=False),
        sa.Column("refresh_token_enc", sa.Text),
        sa.Column("access_expires_at", sa.DateTime(timezone=True)),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    for table in (
        "ebay_tokens",
        "jobs",
        "templates",
        "pricing_rules",
        "sales_history",
        "listing_images",
        "listings",
        "fitment",
        "parts",
        "users",
    ):
        op.drop_table(table)
