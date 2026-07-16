"""Sold history & relist (spec §11) + sale detection (spec §10 order polling).

- archive_sale writes the immutable sales_history row: denormalized part
  number, retained image paths, fitment snapshot — survives part edits.
- sync_ebay_orders polls the Sell Fulfillment API and archives line items
  whose SKU matches a listed listing (SKU == listing id, our correlation id).
- relist_from_history creates a fresh draft that REUSES the original images
  (no re-photographing) and re-runs current pricing (market moves).
"""
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Listing, ListingImage, Part, SalesHistory
from app.services.ebay import EbayClient

logger = logging.getLogger(__name__)


async def archive_sale(
    db: AsyncSession,
    listing: Listing,
    *,
    sold_price: Decimal | float | None,
    sold_date: datetime | None = None,
    buyer_ref: str | None = None,
) -> SalesHistory:
    part: Part | None = None
    if listing.part_id is not None:
        part = await db.get(Part, listing.part_id)
    row = SalesHistory(
        part_id=listing.part_id,
        original_listing_id=listing.id,
        part_number=part.part_number if part else None,  # denormalized (spec §5)
        title=listing.title,
        description=listing.description,
        sold_price=Decimal(str(sold_price)) if sold_price is not None else listing.price,
        sold_date=sold_date or datetime.now(timezone.utc),
        image_paths=[img.storage_path for img in listing.images],  # retained (spec §11)
        buyer_ref=buyer_ref,
        fitment_snapshot=[
            {
                "make": f.make,
                "model": f.model,
                "year_start": f.year_start,
                "year_end": f.year_end,
                "confirmed": f.confirmed,
            }
            for f in (part.fitment if part else [])
        ],
    )
    listing.status = "sold"
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def relist_from_history(db: AsyncSession, history: SalesHistory) -> Listing:
    """One-click relist (spec §11): fresh draft, original photos, current pricing."""
    original: Listing | None = None
    if history.original_listing_id is not None:
        original = (
            await db.execute(select(Listing).where(Listing.id == history.original_listing_id))
        ).scalar_one_or_none()

    new = Listing(
        status="draft",
        part_id=history.part_id,
        title=(history.title or "")[:80] or None,
        description=history.description,
        category_id=original.category_id if original else None,
        item_specifics=original.item_specifics if original else None,
        condition=original.condition if original else None,
        quantity=1,
    )
    db.add(new)
    await db.flush()
    for img in (original.images if original else []):
        db.add(
            ListingImage(
                listing_id=new.id,
                part_id=new.part_id,
                storage_path=img.storage_path,  # same object — no re-upload, no copy
                content_type=img.content_type,
                is_primary=img.is_primary,
                order_index=img.order_index,
            )
        )
    await db.commit()
    await db.refresh(new)

    from app.services import pricing  # re-run CURRENT pricing — the market moved

    try:
        result = await pricing.price_listing(db, new)
        await pricing.apply_pricing(db, new, result)
    except Exception:
        logger.exception("relist pricing failed for %s", new.id)
    await db.refresh(new)
    return new


async def apply_orders(db: AsyncSession, payload: dict) -> dict:
    """Map a Fulfillment API orders payload onto listings (SKU == listing id)."""
    archived = 0
    orders = payload.get("orders") or []
    for order in orders:
        sold_date = None
        if order.get("creationDate"):
            try:
                sold_date = datetime.fromisoformat(order["creationDate"].replace("Z", "+00:00"))
            except ValueError:
                pass
        buyer = (order.get("buyer") or {}).get("username")
        for item in order.get("lineItems") or []:
            sku = item.get("sku") or ""
            try:
                listing_id = uuid.UUID(sku)
            except ValueError:
                continue
            listing = (
                await db.execute(select(Listing).where(Listing.id == listing_id))
            ).scalar_one_or_none()
            if listing is None or listing.status != "listed":
                continue
            total = (item.get("total") or {}).get("value")
            await archive_sale(
                db, listing, sold_price=total, sold_date=sold_date, buyer_ref=buyer
            )
            archived += 1
    return {"orders_seen": len(orders), "sales_archived": archived}


async def sync_ebay_orders(db: AsyncSession, *, days: int = 7) -> dict:
    """Poll recent orders (spec §10). Raises EbayNotConfigured/NotConnected upstream."""
    client = EbayClient()
    token = await client._access_token(db)
    async with httpx.AsyncClient(timeout=60) as http:
        resp = await http.get(
            f"{client.api_base}/sell/fulfillment/v1/order",
            params={"limit": "100", "filter": f"lastmodifieddate:[{_iso_days_ago(days)}..]"},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        payload = resp.json()
    return await apply_orders(db, payload)


def _iso_days_ago(days: int) -> str:
    from datetime import timedelta

    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
