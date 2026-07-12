"""Data model — spec §5. All tables carry id/created_at/updated_at.

Cross-database types (JSON, Uuid) are used so the suite runs on SQLite while
production runs on Supabase Postgres via the Alembic migration.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, Uuid
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class TimestampMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="owner")  # owner | assistant
    supabase_sub: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)


class Part(TimestampMixin, Base):
    """Canonical record for a known part — the seller's growing catalog (his moat)."""

    __tablename__ = "parts"

    part_number: Mapped[str] = mapped_column(String(64), index=True)  # normalized
    part_number_display: Mapped[str | None] = mapped_column(String(64))
    brand: Mapped[str | None] = mapped_column(String(64))
    part_type: Mapped[str | None] = mapped_column(String(120))
    title_template: Mapped[str | None] = mapped_column(String(120))
    description_template: Mapped[str | None] = mapped_column(Text)
    default_category_id: Mapped[str | None] = mapped_column(String(32))
    item_specifics: Mapped[dict | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="ai_generated")  # ai_generated | imported | manual

    fitment: Mapped[list["Fitment"]] = relationship(back_populates="part", lazy="selectin")


class Fitment(TimestampMixin, Base):
    __tablename__ = "fitment"

    part_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parts.id"), index=True)
    make: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(120))
    year_start: Mapped[int | None] = mapped_column(Integer)
    year_end: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))  # 0-1
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    part: Mapped[Part] = relationship(back_populates="fitment")


class Listing(TimestampMixin, Base):
    __tablename__ = "listings"

    part_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("parts.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    # draft | pending_review | listed | ended | sold | error
    ebay_listing_id: Mapped[str | None] = mapped_column(String(40))
    title: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    price_floor: Mapped[float | None] = mapped_column(Numeric(10, 2))
    computed_competitor_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    undercut_pct: Mapped[float | None] = mapped_column(Numeric(4, 2))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    category_id: Mapped[str | None] = mapped_column(String(32))
    item_specifics: Mapped[dict | None] = mapped_column(JSON)
    shipping_policy_id: Mapped[str | None] = mapped_column(String(40))
    return_policy_id: Mapped[str | None] = mapped_column(String(40))
    payment_policy_id: Mapped[str | None] = mapped_column(String(40))
    condition: Mapped[str | None] = mapped_column(String(60))
    condition_notes: Mapped[str | None] = mapped_column(Text)
    ai_confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))
    needs_human_review: Mapped[bool] = mapped_column(Boolean, default=False)
    price_source: Mapped[str | None] = mapped_column(String(40))  # spec §7.1 transparency
    hint: Mapped[str | None] = mapped_column(String(200))

    part: Mapped[Part | None] = relationship(lazy="selectin")
    images: Mapped[list["ListingImage"]] = relationship(
        back_populates="listing", lazy="selectin", order_by="ListingImage.order_index"
    )


class ListingImage(TimestampMixin, Base):
    __tablename__ = "listing_images"

    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id"), index=True)
    part_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("parts.id"), index=True)
    storage_path: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(100), default="image/jpeg")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    processed_path: Mapped[str | None] = mapped_column(String(500))

    listing: Mapped[Listing] = relationship(back_populates="images")


class SalesHistory(TimestampMixin, Base):
    """Immutable archive of every sale (spec §11). Populated in Phase 3."""

    __tablename__ = "sales_history"

    part_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("parts.id"), index=True)
    original_listing_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("listings.id"))
    part_number: Mapped[str | None] = mapped_column(String(64), index=True)  # denormalized
    title: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    sold_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    sold_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    image_paths: Mapped[list | None] = mapped_column(JSON)
    buyer_ref: Mapped[str | None] = mapped_column(String(120))
    fitment_snapshot: Mapped[list | None] = mapped_column(JSON)


class PricingRule(TimestampMixin, Base):
    """Spec §5/§7 — consumed by the Phase 2 pricing engine."""

    __tablename__ = "pricing_rules"

    scope: Mapped[str] = mapped_column(String(20), default="global")  # global | category | part
    scope_ref: Mapped[str | None] = mapped_column(String(64))
    undercut_pct_min: Mapped[float] = mapped_column(Numeric(4, 2), default=5)
    undercut_pct_max: Mapped[float] = mapped_column(Numeric(4, 2), default=10)
    price_ending: Mapped[str] = mapped_column(String(8), default=".95")
    floor_absolute: Mapped[float | None] = mapped_column(Numeric(10, 2))
    floor_margin_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    free_shipping_threshold: Mapped[float | None] = mapped_column(Numeric(10, 2))


class Template(TimestampMixin, Base):
    __tablename__ = "templates"

    name: Mapped[str] = mapped_column(String(120))
    part_type: Mapped[str | None] = mapped_column(String(120))
    shipping_policy_id: Mapped[str | None] = mapped_column(String(40))
    return_policy_id: Mapped[str | None] = mapped_column(String(40))
    payment_policy_id: Mapped[str | None] = mapped_column(String(40))
    description_boilerplate: Mapped[str | None] = mapped_column(Text)
    item_specifics_defaults: Mapped[dict | None] = mapped_column(JSON)


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"

    type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    # queued | running | succeeded | failed
    payload: Mapped[dict | None] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)


class EbayToken(TimestampMixin, Base):
    """OAuth tokens, Fernet-encrypted at rest (spec §10/§15). Never logged."""

    __tablename__ = "ebay_tokens"

    environment: Mapped[str] = mapped_column(String(20), unique=True)  # sandbox | production
    access_token_enc: Mapped[str] = mapped_column(Text)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text)
    access_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refresh_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
