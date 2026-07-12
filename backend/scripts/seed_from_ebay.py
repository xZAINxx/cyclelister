"""ONE-OFF catalog seeding from the seller's public eBay store pages.

Samples listing titles/prices from ebay.com/str/dscycleconnection and turns
them into the importer CSV (parts + best-effort fitment + price notes).

This is spec §9.1 groundwork tooling, NOT part of the application runtime —
spec §9 explicitly forbids hard-depending on scraping. The durable ingestion
paths remain the eBay APIs (once the seller's keyset exists) and a MotoLister
export. Run occasionally, by hand:

    python scripts/seed_from_ebay.py --pages 3            # fetch + parse + CSV
    python scripts/import_listings.py ../data/seed/dscycleconnection-sample.csv

Outputs (committed for reproducibility):
    data/seed/dscycleconnection-sample.jsonl   raw {id,title,price} per listing
    data/seed/dscycleconnection-sample.csv     importer-format rows
"""
import argparse
import csv
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import httpx

STORE_URL = "https://www.ebay.com/str/dscycleconnection?_ipg=240&_pgn={page}"
# eBay serves an empty shell to minimal client fingerprints (plain urllib) —
# browser-like headers are required.
FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Spec §2 brands (the catalog's brand field); other makes still import brandless.
KNOWN_BRANDS = {
    "yamaha": "Yamaha",
    "honda": "Honda",
    "suzuki": "Suzuki",
    "kawasaki": "Kawasaki",
    "harley": "Harley-Davidson",
    "harley-davidson": "Harley-Davidson",
    "polaris": "Polaris",
    "can-am": "Can-Am",
    "sea-doo": "Sea-Doo",
    "seadoo": "Sea-Doo",
}

# OEM part-number shapes, most specific first. A marker (PART#/OEM #/P/N) wins.
_MARKER_RE = re.compile(
    r"(?:PART\s*#|OEM\s*#?|P/N|#)\s*:?\s*([A-Z0-9]{2,6}(?:-[A-Z0-9]{2,7}){1,3})", re.I
)
_PATTERN_RES = [
    re.compile(r"\b[0-9A-Z]{2,3}-[0-9A-Z]{4,6}-[0-9A-Z]{2}(?:-[0-9A-Z]{2})?\b"),  # Yamaha alnum
    re.compile(r"\b\d{5}-\d{5}-\d{2}\b"),  # Yamaha numeric 5-5-2
    re.compile(r"\b\d{5}-[0-9A-Z]{3}-\d{3}\b"),  # Honda
    re.compile(r"\b\d{5}-\d{4,6}\b"),  # Suzuki / Kawasaki 5-4+
    re.compile(r"\b\d{5}-\d{3}\b"),  # Kawasaki 5-3
    re.compile(r"\b\d{3}[A-Z]\d{4}\b"),  # Kawasaki oddballs: 670B2014, 482K0200
    re.compile(r"\b\d{5}-\d{2}[A-Z]{0,2}\b"),  # Harley: 54708-65, 62125-55BC
]

# Model tokens like XS650, KZ1000, CB750K, GL1100, DT250 — letters then digits.
_MODEL_RE = re.compile(r"^[A-Z]{1,4}\d{2,4}[A-Z]{0,3}$")
_YEAR_RANGE_RE = re.compile(r"^'?(\d{2}|\d{4})\s*[-–/&]\s*'?(\d{2}|\d{4})$")
_YEAR_RE = re.compile(r"^'?(19\d{2}|20\d{2})$")


def _expand_year(y: str) -> int:
    n = int(y)
    if n >= 1000:
        return n
    return 1900 + n if n >= 40 else 2000 + n


def extract_part_number(title: str) -> str | None:
    """Best-effort OEM part number from a listing title. Never invents one."""
    m = _MARKER_RE.search(title)
    if m:
        return m.group(1).upper()
    upper = title.upper()
    candidates: list[tuple[int, int, str]] = []
    for pattern in _PATTERN_RES:
        for match in pattern.finditer(upper):
            candidates.append((len(match.group(0)), match.start(), match.group(0)))
    if not candidates:
        return None
    # Longest wins (a 5-5-2 must beat its own 5-5 prefix); ties -> latest in title.
    candidates.sort(key=lambda c: (c[0], c[1]))
    return candidates[-1][2]


def extract_brand(title: str) -> str | None:
    for word in re.split(r"[\s,/]+", title.lower()):
        if word in KNOWN_BRANDS:
            return KNOWN_BRANDS[word]
    return None


def extract_condition(title: str) -> str:
    t = title.upper()
    if "NOS" in t.split() or "NOS" in t:
        return "new_nos"
    if "NEW" in t.split():
        return "new_other"
    return "used"


def extract_fitment(title: str, brand: str | None) -> list[dict]:
    """Model + adjacent year(-range) pairs only — no guessing (spec §8.3 spirit).

    Recognizes "76-79 GL1000", "GL1000 1978-1984", "1974-1975 CR125" adjacency.
    A model token with no adjacent year info yields nothing; make requires a
    known brand.
    """
    if not brand:
        return []
    tokens = [t.strip(",()") for t in title.replace("'", " '").split()]
    out, seen = [], set()
    for i, tok in enumerate(tokens):
        up = tok.upper()
        if not _MODEL_RE.match(up) or extract_part_number(tok):
            continue
        if up.rstrip("S") in {"NOS", "OEM", "QTY", "PART"}:
            continue
        years = None
        for j in (i - 1, i + 1, i - 2, i + 2):  # closest neighbors first
            if 0 <= j < len(tokens):
                mr = _YEAR_RANGE_RE.match(tokens[j])
                my = _YEAR_RE.match(tokens[j])
                if mr:
                    years = (_expand_year(mr.group(1)), _expand_year(mr.group(2)))
                    break
                if my:
                    y = _expand_year(my.group(1))
                    years = (y, y)
                    break
        if years and (brand, up, years) not in seen:
            seen.add((brand, up, years))
            out.append(
                {"make": brand, "model": up, "year_start": years[0], "year_end": years[1]}
            )
    return out


def parse_listing(item: dict) -> dict | None:
    """Raw {id,title,price} -> importer CSV row, or None when no part number."""
    title = (item.get("title") or "").strip()
    part_number = extract_part_number(title)
    if not part_number:
        return None
    brand = extract_brand(title)
    fitment = extract_fitment(title, brand)
    condition = extract_condition(title)
    notes = (
        f"Seeded from eBay item {item.get('id')} on {date.today().isoformat()}; "
        f"listed at {item.get('price') or 'n/a'}; condition signal: {condition}"
    )
    return {
        "part_number": part_number,
        "brand": brand or "",
        "part_type": "",  # titles are too noisy for reliable type; AI fills on relist
        "title": title[:120],
        "description": "",
        "category_id": "",
        "fitment": ";".join(
            f"{f['make']}|{f['model']}|{f['year_start']}|{f['year_end']}" for f in fitment
        ),
        "notes": notes,
    }


def fetch_page(page: int) -> list[dict]:
    resp = httpx.get(
        STORE_URL.format(page=page), headers=FETCH_HEADERS, timeout=45, follow_redirects=True
    )
    resp.raise_for_status()
    html = resp.text
    items = []
    for chunk in re.split(r"<article\b", html)[1:]:
        m_id = re.search(r'"itm":"(\d+)"', chunk)
        m_title = re.search(r'aria-label="watch ([^"]+)"', chunk)
        m_price = re.search(r"\$[\d,]+\.\d{2}", chunk)
        if m_title:
            items.append(
                {
                    "id": m_id.group(1) if m_id else None,
                    "title": m_title.group(1).strip(),
                    "price": m_price.group(0) if m_price else None,
                }
            )
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument(
        "--out-dir", default=str(Path(__file__).resolve().parent.parent.parent / "data" / "seed")
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw: list[dict] = []
    for page in range(1, args.pages + 1):
        items = fetch_page(page)
        if not items:  # eBay intermittently serves an empty variant — one retry
            time.sleep(5)
            items = fetch_page(page)
        print(f"page {page}: {len(items)} listings")
        raw.extend(items)
        if page < args.pages:
            time.sleep(2)  # be polite — this is the client's own store, sampled rarely

    jsonl_path = out_dir / "dscycleconnection-sample.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as fh:
        for item in raw:
            fh.write(json.dumps(item) + "\n")

    rows = [r for r in (parse_listing(i) for i in raw) if r]
    if not rows:
        print("no listings extracted — eBay may be rate-limiting; try again later")
        return 1
    csv_path = out_dir / "dscycleconnection-sample.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    with_fitment = sum(1 for r in rows if r["fitment"])
    print(
        f"captured {len(raw)} listings -> {len(rows)} with part numbers "
        f"({with_fitment} with fitment) -> {csv_path}"
    )


if __name__ == "__main__":
    sys.exit(main())
