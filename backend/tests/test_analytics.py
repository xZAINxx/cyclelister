def test_analytics_summary_shape_and_counts(client):
    before = client.get("/api/analytics/summary").json()
    client.post("/api/listings", json={"hint": "analytics probe"})
    after = client.get("/api/analytics/summary").json()

    for group in ("operations", "sales", "ai", "inventory"):
        assert group in after

    assert after["operations"]["created_7d"] == before["operations"]["created_7d"] + 1
    assert len(after["operations"]["by_week"]) == 8
    assert after["sales"]["connected"] is False
    assert after["ai"]["est_cost_total_usd"] >= 0
    assert after["inventory"]["parts_total"] >= 0
    assert 0 <= after["inventory"]["fitment_coverage"] <= 1
