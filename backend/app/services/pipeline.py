"""The listing pipeline (spec §6): identify -> catalog match -> fitment -> generate -> assemble.

Design rules honored:
- resumable: each step commits; a failure leaves the draft with completed steps intact
- nothing is auto-published; the pipeline ends at status=pending_review
- pricing is Phase 2: price stays empty and the seller sets it on the review screen
"""
import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Listing, Part
from app.db.session import get_session_factory
from app.services import catalog
from app.services.ai import AIService, GenerateResult, IdentifyResult
from app.services.storage import get_storage

logger = logging.getLogger(__name__)

REVIEW_CONFIDENCE_THRESHOLD = 0.6


async def _load_listing(session: AsyncSession, listing_id: uuid.UUID) -> Listing:
    listing = (
        await session.execute(select(Listing).where(Listing.id == listing_id))
    ).scalar_one()
    return listing


async def run_listing_pipeline(listing_id: uuid.UUID) -> dict:
    """Job entrypoint. Returns the job result payload (steps + token usage)."""
    steps: dict[str, str] = {}
    ai = AIService()  # raises AIUnavailableError with a clear message if unconfigured
    factory = get_session_factory()

    # ---- Step 2: AI identification -------------------------------------------------
    async with factory() as session:
        listing = await _load_listing(session, listing_id)
        if not listing.images:
            raise ValueError("listing has no images to identify")
        storage = get_storage()
        blobs = await asyncio.gather(
            *(storage.read(img.storage_path) for img in listing.images)
        )
        images = list(zip(blobs, [img.content_type for img in listing.images]))
        identify: IdentifyResult = await ai.identify_part(images, hint=listing.hint)
        listing.ai_confidence = identify.confidence
        listing.condition = identify.condition.grade
        listing.condition_notes = identify.condition.notes or None
        if identify.confidence < REVIEW_CONFIDENCE_THRESHOLD or not identify.part_numbers:
            listing.needs_human_review = True
        await session.commit()
        steps["identify"] = "done"

    # ---- Step 3: catalog match (hit = fast path, miss grows the catalog) -----------
    part_id: uuid.UUID | None = None
    catalog_hit = False
    async with factory() as session:
        listing = await _load_listing(session, listing_id)
        if identify.part_numbers:
            raw_pn = identify.part_numbers[0]
            part = await catalog.match_part(session, raw_pn)
            if part is not None:
                catalog_hit = True
            else:
                part = await catalog.create_part(
                    session, raw_pn, brand=identify.brand, part_type=identify.part_type
                )
            listing.part_id = part.id
            part_id = part.id
            if catalog_hit:
                # reuse stored knowledge (spec §6 step 3 fast path)
                listing.category_id = listing.category_id or part.default_category_id
                if part.item_specifics:
                    listing.item_specifics = {
                        **part.item_specifics,
                        **(listing.item_specifics or {}),
                    }
        await session.commit()
        steps["catalog_match"] = "hit" if catalog_hit else ("new_part" if part_id else "no_part_number")

    # ---- Step 4 + 6: fitment resolution and listing generation ---------------------
    async with factory() as session:
        listing = await _load_listing(session, listing_id)
        part: Part | None = None
        known_fitment: list[dict] = []
        boilerplate = None
        specifics_defaults = None
        if part_id is not None:
            part = (await session.execute(select(Part).where(Part.id == part_id))).scalar_one()
            known_fitment = [
                {
                    "make": f.make,
                    "model": f.model,
                    "year_start": f.year_start,
                    "year_end": f.year_end,
                }
                for f in part.fitment
                if f.confirmed
            ]
            boilerplate = part.description_template
            specifics_defaults = part.item_specifics

        generated: GenerateResult = await ai.generate_listing(
            part_number_display=(part.part_number_display if part else None)
            or (identify.part_numbers[0] if identify.part_numbers else None),
            part_type=(part.part_type if part else None) or identify.part_type,
            brand=(part.brand if part else None) or identify.brand,
            condition=identify.condition,
            known_fitment=known_fitment,
            hint=listing.hint,
            boilerplate=boilerplate,
            item_specifics_defaults=specifics_defaults,
        )

        listing.title = generated.title  # <=80 enforced by the GenerateResult validator
        listing.description = generated.description
        listing.item_specifics = {**generated.item_specifics, **(listing.item_specifics or {})}
        listing.category_id = listing.category_id or generated.suggested_category

        if part is not None:
            # learn back into the catalog (spec §6 step 8 note)
            part.title_template = part.title_template or listing.title
            if part.description_template is None:
                part.description_template = listing.description
            if part.default_category_id is None:
                part.default_category_id = listing.category_id
            # AI fitment suggestions: stored unconfirmed with confidence (spec §8.3/§9)
            catalog.merge_fitment(
                session,
                part.id,
                part.fitment,
                [
                    {
                        "make": sug.make,
                        "model": sug.model,
                        "year_start": sug.year_start,
                        "year_end": sug.year_end,
                        "confidence": sug.confidence,
                        "confirmed": False,
                    }
                    for sug in generated.fitment_suggestions
                ],
            )
        await session.commit()
        steps["generate"] = "done"

    # ---- Step 5: pricing (spec §7) ---------------------------------------------------
    async with factory() as session:
        listing = await _load_listing(session, listing_id)
        try:
            from app.services import pricing

            result = await pricing.price_listing(session, listing)
            await pricing.apply_pricing(session, listing, result)
            steps["price"] = result.price_source
        except Exception as err:  # pricing failure never blocks the draft (§6 resumable)
            logger.exception("pricing failed for %s", listing_id)
            listing.needs_human_review = True
            listing.price_explanation = f"Pricing failed ({err}); set price manually"
            await session.commit()
            steps["price"] = "failed"

    # ---- Step 7: assemble draft -----------------------------------------------------
    async with factory() as session:
        listing = await _load_listing(session, listing_id)
        listing.status = "pending_review"
        await session.commit()
        steps["assemble"] = "done"

    return {"steps": steps, "ai_usage": ai.usage_log}
