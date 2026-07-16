"""Pricing engine through the API: sold-history, no-source, thin-market, undercut."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.db.models import PricingRule, SalesHistory
from app.services import pricing as pricing_module
from app.services.catalog import normalize_part_number
from app.services.pricing import Comp


def run_db(coro_fn):
    """Run an async DB operation on a dedicated engine/loop (test-side seeding)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.config import get_settings

    async def runner():
        engine = create_async_engine(get_settings().database_url)
        try:
            async with async_sessionmaker(engine)() as session:
                await coro_fn(session)
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(runner())


@pytest.fixture()
def seeded_sales(client):
    async def seed(session):
        for p in ("14.95", "13.95", "15.95"):
            session.add(
                SalesHistory(
                    part_number=normalize_part_number("3G2-83312-00"),
                    title="Yamaha NOS Carburetor 3G2-83312-00",
                    sold_price=Decimal(p),
                    sold_date=datetime.now(timezone.utc),
                )
            )

    run_db(seed)


def test_reprice_without_any_source_flags_review(client):
    listing = client.post("/api/listings", json={"hint": "mystery part"}).json()
    body = client.post(f"/api/listings/{listing['id']}/price").json()
    assert body["price"] is None
    assert body["needs_human_review"] is True
    assert "manually" in body["price_explanation"]


def test_thin_market_suggests_without_undercut(client, monkeypatch):
    class FakeBrowse:
        available = True

        async def get_active_comps(self, part_number, keywords, category):
            return [Comp(price=Decimal("20.00"), title="mystery widget thing", source="ebay_browse")]

    monkeypatch.setattr(pricing_module, "BrowseApiSource", lambda *a, **k: FakeBrowse())
    listing = client.post("/api/listings", json={}).json()
    client.patch(f"/api/listings/{listing['id']}", json={"title": "mystery widget thing"})
    body = client.post(f"/api/listings/{listing['id']}/price").json()
    assert body["price"] == 19.95  # round_to_95(lowest comp), no blind undercut (spec §7.2)
    assert body["needs_human_review"] is True
    assert "review price" in body["price_explanation"]


def test_browse_undercut_matches_spec_worked_example(client, monkeypatch):
    class FakeBrowse:
        available = True

        async def get_active_comps(self, part_number, keywords, category):
            return [
                Comp(price=Decimal(p), title="alpha beta gamma widget", source="ebay_browse")
                for p in ("15.20", "18.00", "22.50")
            ]

    monkeypatch.setattr(pricing_module, "BrowseApiSource", lambda *a, **k: FakeBrowse())

    async def add_rule(session):
        session.add(PricingRule(scope="global", undercut_pct_min=8, undercut_pct_max=8))

    run_db(add_rule)

    listing = client.post("/api/listings", json={}).json()
    client.patch(f"/api/listings/{listing['id']}", json={"title": "alpha beta gamma widget"})
    body = client.post(f"/api/listings/{listing['id']}/price").json()
    assert body["price"] == 13.95  # "$13.95 — 8% below lowest competitor $15.20" (§6 step 8)
    assert body["computed_competitor_price"] == 15.20
    assert body["price_source"] == "ebay_browse"
    assert "15.20" in body["price_explanation"]


def test_reprice_uses_internal_sold_history(client, seeded_sales):
    part = client.get("/api/parts", params={"q": "3G28331200"}).json()["items"][0]
    listing = client.post("/api/listings", json={"part_id": part["id"]}).json()
    body = client.post(f"/api/listings/{listing['id']}/price").json()
    # median of 13.95 / 14.95 / 15.95 = 14.95 -> matched, not undercut
    assert body["price"] == 14.95
    assert body["price_source"] == "internal_history"
    assert "sold-history" in body["price_explanation"]
    assert body["needs_human_review"] is False  # 3 sales = confident
