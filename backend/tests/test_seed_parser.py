"""Unit tests for the eBay-title parser used by the one-off seeding script."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from seed_from_ebay import (  # noqa: E402
    extract_brand,
    extract_condition,
    extract_fitment,
    extract_part_number,
    parse_listing,
)


def test_marker_part_number_wins():
    assert extract_part_number(
        "NOS Kawasaki Tank Cap Fitting Pin H2 S1 PART# 92043-094"
    ) == "92043-094"
    assert extract_part_number(
        "NOS GENUINE HONDA XR600 CARBURETOR T JOINT OEM # 16180-195-731"
    ) == "16180-195-731"


def test_yamaha_pattern():
    assert extract_part_number(
        "NOS YAMAHA AT1 BW80 DT1 GASKET 90430-12207-00"
    ) == "90430-12207-00"


def test_kawasaki_oddball_pattern():
    assert extract_part_number("NOS KAWASAKI O RING 14MM VN800 670B2014") == "670B2014"


def test_no_part_number_returns_none():
    assert extract_part_number("NEW HARLEY DAVIDSON Chrome Star Wheel Cover") is None
    assert extract_part_number("OEM ITALJET MINI BIKE RED KICKSTAND") is None


def test_brand_detection():
    assert extract_brand("NOS Yamaha Side Cover Grommet") == "Yamaha"
    assert extract_brand("NOS SCM Chrome Petcock Harley Davidson Wing") == "Harley-Davidson"
    assert extract_brand("SIERRA 18-0118 REPLACES OMC CARBURETOR GASKET") is None


def test_condition_detection():
    assert extract_condition("NOS HONDA FUSE #38201-VH7-B00") == "new_nos"
    assert extract_condition("NEW Genuine Can-Am Maverick Mirror") == "new_other"
    assert extract_condition("Kawasaki Tank Bag Mossy Oak Camo") == "used"


def test_fitment_year_range_before_model():
    fits = extract_fitment(
        "NOS GENUINE Honda 76-79 GL1000 O Ring OEM # 91345-580-000", "Honda"
    )
    assert {"make": "Honda", "model": "GL1000", "year_start": 1976, "year_end": 1979} in fits


def test_fitment_year_range_after_model():
    fits = extract_fitment(
        "NOS HONDA CR125MA ELSINORE 1974-1975 CLUTCH ARM OEM # 22810-360-010", "Honda"
    )
    assert any(f["model"] == "CR125MA" and f["year_start"] == 1974 and f["year_end"] == 1975 for f in fits)


def test_fitment_requires_adjacent_years():
    # models present but no year info -> no fitment rows (never guess)
    assert extract_fitment("NOS HONDA CB CL SL 125 PISTON PIN CLIP 94601-15000", "Honda") == []


def test_fitment_requires_brand():
    assert extract_fitment("NOS 76-79 GL1000 O Ring", None) == []


def test_parse_listing_row():
    row = parse_listing(
        {
            "id": "266790388207",
            "title": "NOS GENUINE Yamaha Side Cover Grommet 76-77 XS360 90480-01401",
            "price": "$4.95",
        }
    )
    assert row["part_number"] == "90480-01401"
    assert row["brand"] == "Yamaha"
    assert "$4.95" in row["notes"]
    assert "Yamaha|XS360|1976|1977" in row["fitment"]


def test_parse_listing_without_part_number_is_skipped():
    assert parse_listing({"id": "1", "title": "Chrome thing for a bike", "price": "$9.95"}) is None
