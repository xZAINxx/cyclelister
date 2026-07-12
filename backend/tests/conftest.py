import os
import tempfile

import pytest

_TMP = tempfile.mkdtemp(prefix="cyclelister-test-")
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP}/test.db"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["STORAGE_DIR"] = f"{_TMP}/images"
os.environ["SUPABASE_JWT_SECRET"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["EBAY_CLIENT_ID"] = ""
os.environ["EBAY_CLIENT_SECRET"] = ""
os.environ["EBAY_TOKEN_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
