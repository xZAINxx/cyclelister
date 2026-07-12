"""Pluggable object storage (spec §4): local disk for dev, Supabase Storage for prod."""
from pathlib import Path
from typing import Protocol

import httpx

from app.config import Settings, get_settings


class Storage(Protocol):
    async def save(self, key: str, data: bytes, content_type: str) -> str: ...
    async def read(self, key: str) -> bytes: ...
    def public_url(self, key: str) -> str | None:
        """Publicly reachable URL, or None when the backend can't provide one."""
        ...


class LocalDiskStorage:
    def __init__(self, root: str):
        self.root = Path(root)

    async def save(self, key: str, data: bytes, content_type: str) -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    async def read(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def public_url(self, key: str) -> str | None:
        return None  # eBay publish requires publicly hosted images; see ebay.py


class SupabaseStorage:
    """Supabase Storage over its REST API (service-role key, server-side only)."""

    def __init__(self, base_url: str, service_key: str, bucket: str):
        self.base_url = base_url.rstrip("/")
        self.bucket = bucket
        self._headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        # One connection pool for the process lifetime (this object is a singleton).
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60, headers=self._headers)
        return self._client

    async def save(self, key: str, data: bytes, content_type: str) -> str:
        resp = await self._http().post(
            f"{self.base_url}/storage/v1/object/{self.bucket}/{key}",
            content=data,
            headers={"Content-Type": content_type, "x-upsert": "true"},
        )
        resp.raise_for_status()
        return key

    async def read(self, key: str) -> bytes:
        resp = await self._http().get(
            f"{self.base_url}/storage/v1/object/{self.bucket}/{key}"
        )
        resp.raise_for_status()
        return resp.content

    def public_url(self, key: str) -> str | None:
        # Bucket should be public (or fronted by a CDN) for eBay image hosting.
        return f"{self.base_url}/storage/v1/object/public/{self.bucket}/{key}"


_storage: Storage | None = None


def get_storage(settings: Settings | None = None) -> Storage:
    global _storage
    if _storage is None:
        s = settings or get_settings()
        if s.storage_backend == "supabase":
            _storage = SupabaseStorage(s.supabase_url, s.supabase_service_role_key, s.storage_bucket)
        else:
            _storage = LocalDiskStorage(s.storage_dir)
    return _storage


def reset_storage() -> None:
    global _storage
    _storage = None
