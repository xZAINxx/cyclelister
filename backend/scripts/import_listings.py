"""Seed `parts` + `fitment` from a CSV export of existing listings (spec §9.1 groundwork).

Usage:
    python scripts/import_listings.py export.csv

Expected CSV columns (header row required; extra columns ignored):
    part_number, brand, part_type, title, description, category_id, fitment

`fitment` cell format: semicolon-separated entries "Make|Model|year_start|year_end",
years optional, e.g. "Yamaha|XS650|1978|1984;Honda|CB750||".
Imported fitment is marked confirmed (it comes from the seller's own history).
Re-running is safe: existing part numbers are updated, not duplicated.
"""
import asyncio
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models import Base  # noqa: E402
from app.db.session import get_engine, get_session_factory  # noqa: E402
from app.services import catalog  # noqa: E402


def parse_fitment(cell: str) -> list[dict]:
    rows = []
    for entry in (cell or "").split(";"):
        entry = entry.strip()
        if not entry:
            continue
        bits = (entry.split("|") + [None] * 4)[:4]
        make, model, ys, ye = bits
        if not make or not model:
            continue
        rows.append(
            {
                "make": make.strip(),
                "model": model.strip(),
                "year_start": int(ys) if ys and str(ys).strip() else None,
                "year_end": int(ye) if ye and str(ye).strip() else None,
            }
        )
    return rows


async def import_csv(path: str) -> tuple[int, int]:
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    created = updated = 0
    factory = get_session_factory()
    async with factory() as session:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                raw_pn = (row.get("part_number") or "").strip()
                if not raw_pn:
                    continue
                part = await catalog.match_part(session, raw_pn)
                if part is None:
                    part = await catalog.create_part(session, raw_pn, source="imported")
                    created += 1
                else:
                    updated += 1
                part.brand = (row.get("brand") or "").strip() or part.brand
                part.part_type = (row.get("part_type") or "").strip() or part.part_type
                part.title_template = (row.get("title") or "").strip()[:120] or part.title_template
                part.description_template = (row.get("description") or "").strip() or part.description_template
                part.default_category_id = (row.get("category_id") or "").strip() or part.default_category_id

                existing = await part.awaitable_attrs.fitment
                catalog.merge_fitment(
                    session,
                    part.id,
                    existing,
                    [
                        {**f, "confirmed": True, "confidence": 1.0}
                        for f in parse_fitment(row.get("fitment") or "")
                    ],
                )
        await session.commit()
    return created, updated


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    created, updated = asyncio.run(import_csv(sys.argv[1]))
    print(f"Imported: {created} new parts, {updated} updated")
