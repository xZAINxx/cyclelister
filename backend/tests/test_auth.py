"""Auth enforcement: HS256 secret path and ES256 JWKS path, real crypto."""
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app import auth as auth_module
from app.config import Settings, get_settings
from app.main import app


@pytest.fixture()
def enforced_hs256():
    settings = Settings(auth_required=True, supabase_jwt_secret="test-secret")
    app.dependency_overrides[get_settings] = lambda: settings
    yield settings
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture()
def enforced_jwks(monkeypatch):
    settings = Settings(
        auth_required=True, supabase_jwt_secret="", supabase_url="https://example.supabase.co"
    )
    app.dependency_overrides[get_settings] = lambda: settings

    private_key = ec.generate_private_key(ec.SECP256R1())

    class FakeSigningKey:
        key = private_key.public_key()

    class FakeJWKSClient:
        def get_signing_key_from_jwt(self, token):
            return FakeSigningKey()

    monkeypatch.setattr(auth_module, "_jwks_client", lambda url: FakeJWKSClient())
    yield private_key
    app.dependency_overrides.pop(get_settings, None)


def _token(key, alg, **overrides):
    claims = {"sub": str(uuid.uuid4()), "aud": "authenticated", "email": "d@example.com"}
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm=alg)


def test_enforced_rejects_missing_and_garbage_tokens(client, enforced_hs256):
    assert client.get("/api/listings").status_code == 401
    assert (
        client.get("/api/listings", headers={"Authorization": "Bearer garbage"}).status_code == 401
    )


def test_enforced_rejects_wrong_secret(client, enforced_hs256):
    bad = _token("other-secret", "HS256")
    assert client.get("/api/listings", headers={"Authorization": f"Bearer {bad}"}).status_code == 401


def test_enforced_accepts_valid_hs256(client, enforced_hs256):
    good = _token("test-secret", "HS256")
    resp = client.get("/api/listings", headers={"Authorization": f"Bearer {good}"})
    assert resp.status_code == 200


def test_enforced_accepts_valid_es256_via_jwks(client, enforced_jwks):
    good = _token(enforced_jwks, "ES256")
    resp = client.get("/api/listings", headers={"Authorization": f"Bearer {good}"})
    assert resp.status_code == 200


def test_enforced_rejects_wrong_es256_key(client, enforced_jwks):
    other_key = ec.generate_private_key(ec.SECP256R1())
    bad = _token(other_key, "ES256")
    assert client.get("/api/listings", headers={"Authorization": f"Bearer {bad}"}).status_code == 401


def test_health_stays_public(client, enforced_hs256):
    assert client.get("/api/health").status_code == 200


def test_dev_bypass_still_default(client):
    assert client.get("/api/listings").status_code == 200
