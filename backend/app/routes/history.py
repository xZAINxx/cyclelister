"""Sold history: search + one-click relist (spec §11)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db.models import ListingImage, SalesHistory, User
from app.db.session import get_db
from app.schemas import ListingOut
from app.services.catalog import normalize_part_number
from app.services.sales import relist_from_history

router = APIRouter(prefix="/history", tags=["history"])


@router.get("")
async def search_history(
    q: str = "",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    query = select(SalesHistory).order_by(SalesHistory.sold_date.desc()).limit(200)
    if q:
        normalized = normalize_part_number(q)
        clauses = [SalesHistory.title.ilike(f"%{q}%")]
        if normalized:
            clauses.append(SalesHistory.part_number.contains(normalized))
        query = query.where(or_(*clauses))
    rows = (await db.execute(query)).scalars().all()

    # primary thumbnail per row via the original listing's image records
    listing_ids = [r.original_listing_id for r in rows if r.original_listing_id]
    thumbs: dict = {}
    if listing_ids:
        images = (
            await db.execute(
                select(ListingImage)
                .where(ListingImage.listing_id.in_(listing_ids))
                .order_by(ListingImage.order_index)
            )
        ).scalars().all()
        for img in images:
            thumbs.setdefault(img.listing_id, str(img.id))

    return {
        "items": [
            {
                "id": str(r.id),
                "part_number": r.part_number,
                "title": r.title,
                "sold_price": float(r.sold_price) if r.sold_price is not None else None,
                "sold_date": r.sold_date.isoformat() if r.sold_date else None,
                "buyer_ref": r.buyer_ref,
                "image_count": len(r.image_paths or []),
                "thumb_image_id": thumbs.get(r.original_listing_id),
                "fitment_snapshot": r.fitment_snapshot or [],
            }
            for r in rows
        ]
    }


@router.post("/{history_id}/relist", response_model=ListingOut)
async def relist(
    history_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    row = (
        await db.execute(select(SalesHistory).where(SalesHistory.id == history_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="History entry not found")
    listing = await relist_from_history(db, row)
    return ListingOut.from_model(listing)
