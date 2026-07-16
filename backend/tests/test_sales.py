"""Phase 3: archive on sale, searchable history, one-click relist (spec §11)."""
import io

from sqlalchemy import select

from app.db.models import Listing
from app.services import sales as sales_module
from tests.test_api import PNG_BYTES
from tests.test_pricing_api import run_db


def _update_factory(listing_id):
    import uuid

    async def _update(session):
        listing = (
            await session.execute(select(Listing).where(Listing.id == uuid.UUID(listing_id)))
        ).scalar_one()
        listing.status = "listed"

    return _update


def _listed_listing_with_part(client, price="19.95"):
    part = client.get("/api/parts", params={"q": "3G28331200"}).json()["items"][0]
    listing = client.post("/api/listings", json={"part_id": part["id"]}).json()
    client.post(
        f"/api/listings/{listing['id']}/images",
        files={"file": ("sold.png", io.BytesIO(PNG_BYTES), "image/png")},
    )
    client.patch(f"/api/listings/{listing['id']}", json={"price": float(price)})
    run_db(_update_factory(listing["id"]))
    return client.get(f"/api/listings/{listing['id']}").json()


def test_mark_sold_archives_immutable_history(client):
    listing = _listed_listing_with_part(client)
    body = client.post(
        f"/api/listings/{listing['id']}/mark-sold", json={"sold_price": 19.95}
    ).json()
    assert body["status"] == "sold"

    items = client.get("/api/history", params={"q": "3G2-83312-00"}).json()["items"]
    assert items, "sale should be searchable by part number"
    row = items[0]
    assert row["sold_price"] == 19.95
    assert row["part_number"] == "3G28331200"  # denormalized
    assert row["image_count"] == 1  # image paths retained (spec §11)
    assert row["thumb_image_id"]


def test_relist_reuses_images_and_reprices_from_history(client):
    items = client.get("/api/history", params={"q": "3G28331200"}).json()["items"]
    listing = client.post(f"/api/history/{items[0]['id']}/relist").json()

    assert listing["status"] == "draft"
    assert listing["part"] is not None
    assert listing["title"]  # prefilled from history
    assert len(listing["images"]) == 1  # original photo reused, no re-photographing
    # pricing re-ran against sold history (3 pricing-test sales + this one = 4)
    assert listing["price_source"] == "internal_history"
    assert listing["price"] == 14.95  # round_to_95(median 15.45)
    assert listing["needs_human_review"] is False
    assert "sold-history" in listing["price_explanation"]


def test_apply_orders_archives_by_sku(client):
    listing = _listed_listing_with_part(client)

    async def _apply(session):
        result = await sales_module.apply_orders(
            session,
            {
                "orders": [
                    {
                        "creationDate": "2026-07-12T10:00:00.000Z",
                        "buyer": {"username": "moto_buyer_77"},
                        "lineItems": [
                            {"sku": listing["id"], "total": {"value": "21.95"}},
                            {"sku": "not-a-uuid", "total": {"value": "5.00"}},
                        ],
                    }
                ]
            },
        )
        assert result == {"orders_seen": 1, "sales_archived": 1}

    run_db(_apply)
    body = client.get(f"/api/listings/{listing['id']}").json()
    assert body["status"] == "sold"
    items = client.get("/api/history").json()["items"]
    assert any(r["buyer_ref"] == "moto_buyer_77" and r["sold_price"] == 21.95 for r in items)


def test_analytics_reflects_sales(client):
    body = client.get("/api/analytics/summary").json()
    assert body["sales"]["connected"] is True
    assert body["sales"]["revenue_30d"] > 0
    assert body["sales"]["total_sales"] >= 2


def test_mark_sold_requires_live_listing(client):
    listing = client.post("/api/listings", json={}).json()  # draft
    resp = client.post(f"/api/listings/{listing['id']}/mark-sold", json={})
    assert resp.status_code == 409
