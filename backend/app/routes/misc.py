"""Health, jobs, parts, images, and eBay status/OAuth endpoints."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db.models import Fitment, Job, ListingImage, Part, User
from app.db.session import get_db
from app.schemas import EbayStatusOut, FitmentOut, JobOut, PartOut, PutFitmentIn
from app.services.catalog import normalize_part_number
from app.services.ebay import EbayClient, EbayNotConfiguredError
from app.services.storage import get_storage

health_router = APIRouter(tags=["health"])
jobs_router = APIRouter(prefix="/jobs", tags=["jobs"])
parts_router = APIRouter(prefix="/parts", tags=["parts"])
images_router = APIRouter(prefix="/images", tags=["images"])
ebay_router = APIRouter(prefix="/ebay", tags=["ebay"])


@health_router.get("/health")
async def health():
    return {"status": "ok"}


@jobs_router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobOut.model_validate(job)


@parts_router.get("")
async def search_parts(
    q: str = "",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    query = select(Part).order_by(Part.created_at.desc()).limit(50)
    if q:
        normalized = normalize_part_number(q)
        query = query.where(
            or_(Part.part_number.contains(normalized), Part.part_type.ilike(f"%{q}%"))
        )
    parts = (await db.execute(query)).scalars().all()
    return {"items": [PartOut.model_validate(p).model_dump(mode="json") for p in parts]}


@parts_router.put("/{part_id}/fitment")
async def put_fitment(
    part_id: uuid.UUID,
    body: PutFitmentIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """Replace a part's fitment set — the seller's manual override UI (spec §9.4)."""
    part = (await db.execute(select(Part).where(Part.id == part_id))).scalar_one_or_none()
    if part is None:
        raise HTTPException(status_code=404, detail="Part not found")
    await db.execute(delete(Fitment).where(Fitment.part_id == part_id))
    rows = [
        Fitment(
            part_id=part_id,
            make=f.make,
            model=f.model,
            year_start=f.year_start,
            year_end=f.year_end,
            confirmed=f.confirmed,
            confidence=1.0 if f.confirmed else 0.5,
        )
        for f in body.fitments
    ]
    db.add_all(rows)
    await db.commit()
    # no refresh needed: ids/timestamps are client-side defaults, expire_on_commit=False
    return {"items": [FitmentOut.model_validate(r).model_dump(mode="json") for r in rows]}


@images_router.get("/{image_id}")
async def get_image(image_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    # Served without auth so plain <img> tags work; ids are unguessable UUIDs.
    image = (
        await db.execute(select(ListingImage).where(ListingImage.id == image_id))
    ).scalar_one_or_none()
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    data = await get_storage().read(image.storage_path)
    return Response(content=data, media_type=image.content_type)


@ebay_router.get("/status", response_model=EbayStatusOut)
async def ebay_status(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    client = EbayClient()
    return EbayStatusOut(
        configured=client.configured,
        environment=client.settings.ebay_env,
        connected=await client.connected(db),
    )


@ebay_router.get("/oauth/url")
async def ebay_oauth_url(user: User = Depends(current_user)):
    client = EbayClient()
    try:
        return {"url": client.authorize_url()}
    except EbayNotConfiguredError as err:
        raise HTTPException(status_code=503, detail=str(err))


@ebay_router.get("/oauth/callback")
async def ebay_oauth_callback(code: str, db: AsyncSession = Depends(get_db)):
    client = EbayClient()
    try:
        await client.exchange_code(db, code)
    except EbayNotConfiguredError as err:
        raise HTTPException(status_code=503, detail=str(err))
    return Response(
        content="<html><body><h3>eBay connected — you can close this window.</h3></body></html>",
        media_type="text/html",
    )
