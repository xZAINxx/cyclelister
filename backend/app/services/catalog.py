"""Catalog matching (spec §6 step 3), part-number normalization (spec §5),
and the single fitment-merge policy shared by pipeline and importer (spec §9)."""
import re
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Fitment, Part

_NON_ALNUM = re.compile(r"[^A-Z0-9]")


def normalize_part_number(raw: str) -> str:
    """Uppercase and strip spaces/dashes/anything non-alphanumeric for matching."""
    return _NON_ALNUM.sub("", raw.upper())


async def match_part(db: AsyncSession, raw_part_number: str) -> Part | None:
    normalized = normalize_part_number(raw_part_number)
    if not normalized:
        return None
    result = await db.execute(select(Part).where(Part.part_number == normalized))
    return result.scalars().first()


async def create_part(
    db: AsyncSession,
    raw_part_number: str,
    *,
    brand: str | None = None,
    part_type: str | None = None,
    source: str = "ai_generated",
) -> Part:
    """Catalog miss side effect (spec §6 step 3): the catalog grows on its own."""
    part = Part(
        part_number=normalize_part_number(raw_part_number),
        part_number_display=raw_part_number.strip(),
        brand=brand,
        part_type=part_type,
        source=source,
    )
    db.add(part)
    await db.flush()
    return part


def _fitment_key(make: str, model: str, year_start: int | None, year_end: int | None):
    return (make.strip().lower(), model.strip().lower(), year_start, year_end)


def merge_fitment(
    db: AsyncSession,
    part_id,
    existing: Iterable[Fitment],
    entries: Iterable[dict],
) -> list[Fitment]:
    """Add fitment rows not already present on the part.

    `entries` dicts carry make/model/year_start/year_end plus confirmed and
    confidence. Identity is (make, model, year range), case-insensitive —
    keep this the ONLY definition of fitment uniqueness.
    """
    seen = {_fitment_key(f.make, f.model, f.year_start, f.year_end) for f in existing}
    added: list[Fitment] = []
    for entry in entries:
        key = _fitment_key(
            entry["make"], entry["model"], entry.get("year_start"), entry.get("year_end")
        )
        if key in seen:
            continue
        seen.add(key)
        row = Fitment(part_id=part_id, **entry)
        db.add(row)
        added.append(row)
    return added
