"""Catalog browser flow: facets, enriched search, draft-from-part prefill."""


def test_parts_facets(client):
    body = client.get("/api/parts/facets").json()
    assert "brands" in body and "total" in body
    assert body["total"] == sum(b["count"] for b in body["brands"])


def test_search_returns_enriched_rows_and_brand_filter(client):
    items = client.get("/api/parts", params={"q": "3G28331200"}).json()["items"]
    assert items, "expected the part seeded by the pipeline tests"
    row = items[0]
    for key in ("title_template", "notes", "fitment", "source"):
        assert key in row
    filtered = client.get("/api/parts", params={"brand": "Yamaha"}).json()["items"]
    assert all(p["brand"] == "Yamaha" for p in filtered)


def test_create_listing_from_part_prefills(client):
    part = client.get("/api/parts", params={"q": "3G28331200"}).json()["items"][0]
    resp = client.post("/api/listings", json={"part_id": part["id"]})
    assert resp.status_code == 200, resp.text
    listing = resp.json()
    assert listing["part"]["id"] == part["id"]
    assert listing["title"]  # prefilled from the part's title template
    assert listing["status"] == "draft"


def test_create_listing_from_unknown_part_404s(client):
    resp = client.post(
        "/api/listings", json={"part_id": "00000000-0000-0000-0000-000000000000"}
    )
    assert resp.status_code == 404
