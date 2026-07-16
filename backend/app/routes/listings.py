"""Listing endpoints — pipeline steps 1, 7-9 of spec §6."""
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db.models import Listing, ListingImage, User
from app.db.session import get_db
from app.schemas import (
    CreateListingIn,
    ImageOut,
    ListingListOut,
    ListingOut,
    PatchListingIn,
)
from app.services import jobs
from app.services.ebay import (
    EbayClient,
    EbayNotConfiguredError,
    EbayNotConnectedError,
    EbayPublishError,
)
from app.services.pipeline import run_listing_pipeline
from app.services.storage import get_storage

router = APIRouter(prefix="/listings", tags=["listings"])

MAX_IMAGES = 8  # spec §6: 1-8 photos of a single part
MAX_IMAGE_BYTES = 15 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


async def _get_listing(db: AsyncSession, listing_id: uuid.UUID) -> Listing:
    listing = (
        await db.execute(select(Listing).where(Listing.id == listing_id))
    ).scalar_one_or_none()
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


@router.post("", response_model=ListingOut)
async def create_listing(
    body: CreateListingIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    listing = Listing(status="draft", hint=body.hint)
    if body.part_id is not None:
        from app.db.models import Part

        part = await db.get(Part, body.part_id)
        if part is None:
            raise HTTPException(status_code=404, detail="Part not found")
        # Catalog fast path (spec §6 step 3): start the draft 80% done.
        listing.part_id = part.id
        listing.title = (part.title_template or "")[:80] or None
        listing.description = part.description_template
        listing.category_id = part.default_category_id
        listing.item_specifics = part.item_specifics
    db.add(listing)
    await db.commit()
    await db.refresh(listing)
    return ListingOut.from_model(listing)


@router.get("", response_model=ListingListOut)
async def list_listings(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    query = select(Listing).order_by(Listing.created_at.desc()).limit(200)
    if status:
        query = query.where(Listing.status == status)
    listings = (await db.execute(query)).scalars().all()
    return ListingListOut(items=[ListingOut.from_model(l) for l in listings])


@router.get("/{listing_id}", response_model=ListingOut)
async def get_listing(
    listing_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    return ListingOut.from_model(await _get_listing(db, listing_id))


@router.patch("/{listing_id}", response_model=ListingOut)
async def patch_listing(
    listing_id: uuid.UUID,
    body: PatchListingIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    listing = await _get_listing(db, listing_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(listing, field, value)
    await db.commit()
    await db.refresh(listing)
    return ListingOut.from_model(listing)


@router.post("/{listing_id}/images", response_model=ImageOut)
async def upload_image(
    listing_id: uuid.UUID,
    file: UploadFile = File(...),
    order_index: int | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    listing = await _get_listing(db, listing_id)
    if len(listing.images) >= MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"A listing supports at most {MAX_IMAGES} images")
    content_type = file.content_type or "image/jpeg"
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported image type {content_type}")
    data = await file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image exceeds 15 MB")
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    image_id = uuid.uuid4()
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[content_type]
    key = f"listings/{listing.id}/{image_id}.{ext}"
    await get_storage().save(key, data, content_type)

    image = ListingImage(
        id=image_id,
        listing_id=listing.id,
        part_id=listing.part_id,
        storage_path=key,
        content_type=content_type,
        order_index=order_index if order_index is not None else len(listing.images),
        is_primary=len(listing.images) == 0,
    )
    db.add(image)
    await db.commit()
    return ImageOut.from_model(image)


@router.post("/{listing_id}/pipeline")
async def start_pipeline(
    listing_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    listing = await _get_listing(db, listing_id)
    if not listing.images:
        raise HTTPException(status_code=400, detail="Upload at least one image first")
    job_id = await jobs.create_job("listing_pipeline", {"listing_id": str(listing.id)})
    jobs.spawn(job_id, lambda: run_listing_pipeline(listing.id))
    return {"job_id": str(job_id)}


@router.post("/{listing_id}/price", response_model=ListingOut)
async def reprice_listing(
    listing_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """Run the Smart Pricing engine on demand (spec §7; market moves, so can re-run)."""
    from app.services import pricing

    listing = await _get_listing(db, listing_id)
    result = await pricing.price_listing(db, listing)
    await pricing.apply_pricing(db, listing, result)
    await db.refresh(listing)
    return ListingOut.from_model(listing)


@router.post("/{listing_id}/publish", response_model=ListingOut)
async def publish_listing(
    listing_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """Explicit per-listing seller approval (spec §10 guardrails). Never automatic."""
    listing = await _get_listing(db, listing_id)
    if listing.status == "listed":
        raise HTTPException(status_code=409, detail="Listing is already live")
    client = EbayClient()
    try:
        ebay_listing_id = await client.publish_listing(db, listing)
    except (EbayNotConfiguredError, EbayNotConnectedError) as err:
        raise HTTPException(status_code=503, detail=str(err))
    except EbayPublishError as err:
        raise HTTPException(status_code=422, detail=str(err))
    listing.status = "listed"
    listing.ebay_listing_id = ebay_listing_id
    await db.commit()
    await db.refresh(listing)
    return ListingOut.from_model(listing)
