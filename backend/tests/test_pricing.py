"""Smart Pricing engine — pure logic tested hard (spec §15)."""
from decimal import Decimal

from app.services.pricing import (
    Comp,
    RuleSet,
    choose_reference_price,
    filter_comps,
    round_to_95,
    round_up_to_95,
)


# ---- round_to_95: spec §7.3 examples, never-round-up bias ----
def test_round_spec_examples():
    assert round_to_95(13.72) == Decimal("12.95")
    assert round_to_95(249.10) == Decimal("248.95")
    assert round_to_95(4.40) == Decimal("3.95")


def test_round_minimum_is_95_cents():
    assert round_to_95(0.50) == Decimal("0.95")
    assert round_to_95(0) == Decimal("0.95")


def test_round_exact_and_boundaries():
    assert round_to_95(13.95) == Decimal("13.95")
    assert round_to_95(14.00) == Decimal("13.95")
    assert round_to_95(14.94) == Decimal("13.95")
    assert round_to_95(0.95) == Decimal("0.95")


def test_round_up_variant_for_floor_binding():
    assert round_up_to_95(10.50) == Decimal("10.95")
    assert round_up_to_95(9.95) == Decimal("9.95")
    assert round_up_to_95(10.96) == Decimal("11.95")


# ---- undercut math: the spec's own worked example (§6 step 8) ----
def test_spec_worked_example():
    reference = Decimal("15.20")
    target = reference * (Decimal("1") - Decimal("8") / Decimal("100"))
    assert round_to_95(target) == Decimal("13.95")  # "$13.95 — 8% below $15.20"


# ---- comp filtering: spec §7.2 outlier rules ----
def _comp(title, price):
    return Comp(price=Decimal(str(price)), title=title, source="test")


def test_filter_keeps_part_number_matches():
    comps = [_comp("NOS Yamaha grommet 90480-01401 OEM", 4.95)]
    assert len(filter_comps(comps, "90480-01401", "Yamaha grommet")) == 1


def test_filter_drops_bundles_and_junk():
    comps = [
        _comp("Lot of 10 assorted grommets 90480-01401", 19.95),
        _comp("Completely unrelated brake caliper", 44.00),
        _comp("Free item", 0),
    ]
    assert filter_comps(comps, "90480-01401", "Yamaha side cover grommet") == []


def test_filter_keeps_keyword_overlap_without_part_number():
    comps = [_comp("Yamaha XS360 side cover grommet NOS", 5.95)]
    kept = filter_comps(comps, None, "Yamaha side cover grommet")
    assert len(kept) == 1


def test_reference_is_lowest_legitimate():
    comps = [_comp("a 90480-01401", 9.95), _comp("b 90480-01401", 7.95), _comp("c 90480-01401", 12.00)]
    kept = filter_comps(comps, "90480-01401", "x")
    assert choose_reference_price(kept) == Decimal("7.95")


def test_ruleset_defaults():
    rules = RuleSet()
    assert rules.undercut_pct == Decimal("8")
    assert rules.floor is None
