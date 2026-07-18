"""Phase 4: stock location, inventory attention filter (spec §12)."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models import Listing
from tests.test_pricing_api import run_db


def test_stock_location_roundtrip(client):
    listing = client.post("/api/listings", json={}).json()
    body = client.patch(
        f"/api/listings/{listing['id']}", json={"stock_location": "A3-14"}
    ).json()
    assert body["stock_location"] == "A3-14"
    assert client.get(f"/api/listings/{listing['id']}").json()["stock_location"] == "A3-14"


def test_attention_filter_stale_and_zero_stock(client):
    stale = client.post("/api/listings", json={}).json()
    zero = client.post("/api/listings", json={}).json()
    fresh = client.post("/api/listings", json={}).json()

    def _prep(listing_id, *, days_old=0, quantity=1):
        async def _update(session):
            row = (
                await session.execute(
                    select(Listing).where(Listing.id == uuid.UUID(listing_id))
                )
            ).scalar_one()
            row.status = "listed"
            row.quantity = quantity
            row.created_at = datetime.now(timezone.utc) - timedelta(days=days_old)

        return _update

    run_db(_prep(stale["id"], days_old=120))
    run_db(_prep(zero["id"], quantity=0))
    run_db(_prep(fresh["id"], days_old=5))

    ids = {item["id"] for item in client.get("/api/listings", params={"attention": "true"}).json()["items"]}
    assert stale["id"] in ids
    assert zero["id"] in ids
    assert fresh["id"] not in ids
