"""End-to-end API tests with the AI service faked (no network)."""
import io
import time

import pytest

from app.services import pipeline as pipeline_module
from app.services.ai import ConditionInfo, FitmentSuggestion, GenerateResult, IdentifyResult

PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcff9fa10e0002d1017f1d2a2fbd0000000049454e44ae426082"
)


class FakeAI:
    def __init__(self, *args, **kwargs):
        self.usage_log = [{"step": "identify", "model": "fake", "input_tokens": 1, "output_tokens": 1}]

    async def identify_part(self, images, hint=None):
        assert images, "pipeline must pass the uploaded images"
        return IdentifyResult(
            part_numbers=["3G2-83312-00"],
            part_type="carburetor",
            brand="Yamaha",
            condition=ConditionInfo(grade="new_nos", notes="original packaging present"),
            visible_text=["3G2-83312-00"],
            confidence=0.92,
        )

    async def generate_listing(self, **kwargs):
        return GenerateResult(
            title="Yamaha NOS Carburetor 3G2-83312-00 fits XS650 1978-1984",
            description="<p>New Old Stock Yamaha carburetor.</p>",
            item_specifics={"Brand": "Yamaha", "MPN": "3G2-83312-00"},
            suggested_category="10063",
            fitment_suggestions=[
                FitmentSuggestion(make="Yamaha", model="XS650", year_start=1978, year_end=1984, confidence=0.7)
            ],
        )


@pytest.fixture(autouse=True)
def fake_ai(monkeypatch):
    monkeypatch.setattr(pipeline_module, "AIService", FakeAI)


def _upload_image(client, listing_id, name="a.png"):
    return client.post(
        f"/api/listings/{listing_id}/images",
        files={"file": (name, io.BytesIO(PNG_BYTES), "image/png")},
    )


def _run_pipeline(client, listing_id):
    resp = client.post(f"/api/listings/{listing_id}/pipeline")
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]
    for _ in range(100):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError("pipeline job did not finish")


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_create_and_patch_listing(client):
    resp = client.post("/api/listings", json={"hint": "yamaha carb"})
    assert resp.status_code == 200
    listing = resp.json()
    assert listing["status"] == "draft"
    assert listing["hint"] == "yamaha carb"

    resp = client.patch(f"/api/listings/{listing['id']}", json={"price": 12.95, "quantity": 2})
    body = resp.json()
    assert body["price"] == 12.95
    assert body["quantity"] == 2


def test_title_over_80_rejected(client):
    listing = client.post("/api/listings", json={}).json()
    resp = client.patch(f"/api/listings/{listing['id']}", json={"title": "x" * 81})
    assert resp.status_code == 422


def test_image_limit_eight(client):
    listing = client.post("/api/listings", json={}).json()
    for i in range(8):
        resp = _upload_image(client, listing["id"], name=f"img{i}.png")
        assert resp.status_code == 200, resp.text
    resp = _upload_image(client, listing["id"], name="ninth.png")
    assert resp.status_code == 400
    assert "at most 8" in resp.json()["detail"]


def test_rejects_non_image_upload(client):
    listing = client.post("/api/listings", json={}).json()
    resp = client.post(
        f"/api/listings/{listing['id']}/images",
        files={"file": ("evil.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert resp.status_code == 400


def test_pipeline_new_part(client):
    listing = client.post("/api/listings", json={"hint": "found in yamaha bin"}).json()
    assert _upload_image(client, listing["id"]).status_code == 200
    job = _run_pipeline(client, listing["id"])
    assert job["status"] == "succeeded", job["error"]
    assert job["result"]["steps"]["identify"] == "done"
    assert job["result"]["steps"]["catalog_match"] == "new_part"
    assert job["result"]["steps"]["assemble"] == "done"
    assert "ai_usage" in job["result"]

    body = client.get(f"/api/listings/{listing['id']}").json()
    assert body["status"] == "pending_review"
    assert body["title"] and len(body["title"]) <= 80
    assert body["part"]["brand"] == "Yamaha"
    assert body["condition"] == "new_nos"
    # AI fitment suggestion stored unconfirmed with confidence (spec §8.3/§9)
    assert any(f["confirmed"] is False and f["confidence"] == 0.7 for f in body["fitment"])
    # image can be fetched back
    img = client.get(body["images"][0]["url"])
    assert img.status_code == 200
    assert img.content == PNG_BYTES


def test_pipeline_catalog_hit_reuses_part(client):
    # First run created the part (normalized number). Second listing must hit it.
    listing = client.post("/api/listings", json={}).json()
    assert _upload_image(client, listing["id"]).status_code == 200
    job = _run_pipeline(client, listing["id"])
    assert job["status"] == "succeeded"
    assert job["result"]["steps"]["catalog_match"] == "hit"

    body = client.get(f"/api/listings/{listing['id']}").json()
    assert body["part"] is not None

    parts = client.get("/api/parts", params={"q": "3G2-83312-00"}).json()["items"]
    assert len(parts) == 1  # no duplicate part rows


def test_fitment_manual_override(client):
    parts = client.get("/api/parts", params={"q": "3G28331200"}).json()["items"]
    part_id = parts[0]["id"]
    resp = client.put(
        f"/api/parts/{part_id}/fitment",
        json={
            "fitments": [
                {"make": "Yamaha", "model": "XS650", "year_start": 1978, "year_end": 1984, "confirmed": True}
            ]
        },
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["confirmed"] is True


def test_publish_unconfigured_returns_503(client):
    listing = client.post("/api/listings", json={}).json()
    resp = client.post(f"/api/listings/{listing['id']}/publish")
    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"].lower()
    # and the listing did NOT fake success
    body = client.get(f"/api/listings/{listing['id']}").json()
    assert body["status"] != "listed"
    assert body["ebay_listing_id"] is None


def test_ebay_status(client):
    body = client.get("/api/ebay/status").json()
    assert body == {"configured": False, "environment": "sandbox", "connected": False}
