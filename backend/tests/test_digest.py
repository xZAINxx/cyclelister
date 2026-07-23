"""Weekly digest (spec §13): builder over real data, preview, unconfigured send."""


def test_digest_preview_renders_real_totals(client):
    resp = client.get("/api/digest/preview")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    html = resp.text
    assert "CYCLE" in html and "weekly summary" in html
    assert "Top sales this week" in html


def test_digest_send_unconfigured_returns_503(client):
    resp = client.post("/api/digest/send")
    assert resp.status_code == 503
    assert "SMTP_HOST" in resp.json()["detail"]
