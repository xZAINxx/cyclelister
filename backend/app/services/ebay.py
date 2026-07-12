"""eBay integration (spec §10) — modern Sell APIs, OAuth2, sandbox-first.

- OAuth 2.0 authorization-code grant; the app never sees the seller's password.
- Tokens are Fernet-encrypted at rest (spec §15) and never logged.
- Publishing uses Sell Inventory: inventory item -> offer -> publish, keyed on
  the listing id as SKU so a retry never double-lists (idempotent publish).
- When credentials are absent this module raises EbayNotConfiguredError and the
  API surfaces 503 — publish NEVER fake-succeeds.
"""
import base64
import logging
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import EbayToken, Listing
from app.services.storage import get_storage

logger = logging.getLogger(__name__)

OAUTH_SCOPES = " ".join(
    [
        "https://api.ebay.com/oauth/api_scope/sell.inventory",
        "https://api.ebay.com/oauth/api_scope/sell.account",
        "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
    ]
)

CONDITION_MAP = {
    "new_nos": "NEW_OTHER",
    "new_other": "NEW_OTHER",
    "used": "USED_GOOD",
    "for_parts": "FOR_PARTS_OR_NOT_WORKING",
}


class EbayNotConfiguredError(RuntimeError):
    """Credentials missing — surface as 503, never fake success (anti-criterion)."""


class EbayNotConnectedError(RuntimeError):
    """Credentials present but the seller has not completed OAuth."""


class EbayPublishError(RuntimeError):
    pass


class EbayClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    # ---- configuration -------------------------------------------------------------
    @property
    def configured(self) -> bool:
        s = self.settings
        return bool(s.ebay_client_id and s.ebay_client_secret and s.ebay_token_key)

    def _require_configured(self) -> None:
        if not self.configured:
            raise EbayNotConfiguredError(
                "eBay is not configured. Set EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, "
                "EBAY_RU_NAME and EBAY_TOKEN_KEY in the backend environment."
            )

    @property
    def auth_base(self) -> str:
        return (
            "https://auth.sandbox.ebay.com"
            if self.settings.ebay_env == "sandbox"
            else "https://auth.ebay.com"
        )

    @property
    def api_base(self) -> str:
        return (
            "https://api.sandbox.ebay.com"
            if self.settings.ebay_env == "sandbox"
            else "https://api.ebay.com"
        )

    def _fernet(self) -> Fernet:
        return Fernet(self.settings.ebay_token_key.encode())

    def _basic_auth(self) -> str:
        raw = f"{self.settings.ebay_client_id}:{self.settings.ebay_client_secret}"
        return base64.b64encode(raw.encode()).decode()

    # ---- OAuth ----------------------------------------------------------------------
    def authorize_url(self) -> str:
        self._require_configured()
        from urllib.parse import urlencode

        params = urlencode(
            {
                "client_id": self.settings.ebay_client_id,
                "response_type": "code",
                "redirect_uri": self.settings.ebay_ru_name,
                "scope": OAUTH_SCOPES,
            }
        )
        return f"{self.auth_base}/oauth2/authorize?{params}"

    async def _token_request(self, data: dict) -> dict:
        """POST to the OAuth token endpoint (authorization-code and refresh grants)."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.api_base}/identity/v1/oauth2/token",
                headers={
                    "Authorization": f"Basic {self._basic_auth()}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data=data,
            )
            resp.raise_for_status()
            return resp.json()

    async def _token_row(self, db: AsyncSession) -> EbayToken | None:
        return (
            await db.execute(
                select(EbayToken).where(EbayToken.environment == self.settings.ebay_env)
            )
        ).scalar_one_or_none()

    async def exchange_code(self, db: AsyncSession, code: str) -> None:
        self._require_configured()
        payload = await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.settings.ebay_ru_name,
            }
        )
        await self._store_tokens(db, payload)

    async def _store_tokens(self, db: AsyncSession, payload: dict) -> None:
        f = self._fernet()
        now = datetime.now(timezone.utc)
        row = await self._token_row(db)
        if row is None:
            row = EbayToken(environment=self.settings.ebay_env, access_token_enc="")
            db.add(row)
        row.access_token_enc = f.encrypt(payload["access_token"].encode()).decode()
        row.access_expires_at = now + timedelta(seconds=int(payload.get("expires_in", 7200)))
        if payload.get("refresh_token"):
            row.refresh_token_enc = f.encrypt(payload["refresh_token"].encode()).decode()
            row.refresh_expires_at = now + timedelta(
                seconds=int(payload.get("refresh_token_expires_in", 47304000))
            )
        await db.commit()

    async def _access_token(self, db: AsyncSession) -> str:
        self._require_configured()
        row = await self._token_row(db)
        if row is None:
            raise EbayNotConnectedError(
                "eBay account not connected. Visit /api/ebay/oauth/url and authorize the app."
            )
        f = self._fernet()
        now = datetime.now(timezone.utc)
        expires = row.access_expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires is not None and expires > now + timedelta(minutes=2):
            return f.decrypt(row.access_token_enc.encode()).decode()
        if not row.refresh_token_enc:
            raise EbayNotConnectedError("eBay access token expired and no refresh token stored.")
        refresh_token = f.decrypt(row.refresh_token_enc.encode()).decode()
        payload = await self._token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": OAUTH_SCOPES,
            }
        )
        await self._store_tokens(db, payload)
        return payload["access_token"]

    async def connected(self, db: AsyncSession) -> bool:
        if not self.configured:
            return False
        return await self._token_row(db) is not None

    # ---- Publish (Sell Inventory: item -> offer -> publish) -------------------------
    async def publish_listing(self, db: AsyncSession, listing: Listing) -> str:
        token = await self._access_token(db)
        if not listing.title or not listing.description:
            raise EbayPublishError("listing is missing a title or description")
        if listing.price is None:
            raise EbayPublishError("listing has no price set — set one on the review screen")
        if not listing.category_id:
            raise EbayPublishError("listing has no eBay category id")

        storage = get_storage()
        image_urls = [storage.public_url(img.storage_path) for img in listing.images]
        if not image_urls or any(u is None for u in image_urls):
            raise EbayPublishError(
                "eBay requires publicly hosted image URLs. Configure STORAGE_BACKEND=supabase "
                "(local disk storage has no public URLs)."
            )

        sku = str(listing.id)  # correlation id -> idempotent publish (spec §10)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Content-Language": "en-US",
        }
        aspects = {k: [str(v)] for k, v in (listing.item_specifics or {}).items()}
        condition = CONDITION_MAP.get(listing.condition or "used", "USED_GOOD")

        async with httpx.AsyncClient(timeout=60, headers=headers) as client:
            # 1. inventory item (PUT is naturally idempotent on SKU)
            resp = await client.put(
                f"{self.api_base}/sell/inventory/v1/inventory_item/{sku}",
                json={
                    "product": {
                        "title": listing.title,
                        "description": listing.description,
                        "imageUrls": image_urls,
                        "aspects": aspects,
                    },
                    "condition": condition,
                    **(
                        {"conditionDescription": listing.condition_notes}
                        if listing.condition_notes
                        else {}
                    ),
                    "availability": {
                        "shipToLocationAvailability": {"quantity": listing.quantity or 1}
                    },
                },
            )
            if resp.status_code >= 400:
                raise EbayPublishError(f"inventory item failed: {resp.text[:500]}")

            # 2. offer — reuse an existing offer for this SKU on retry
            offer_id: str | None = None
            existing = await client.get(
                f"{self.api_base}/sell/inventory/v1/offer",
                params={"sku": sku, "marketplace_id": self.settings.ebay_marketplace_id},
            )
            if existing.status_code == 200:
                offers = existing.json().get("offers") or []
                if offers:
                    offer_id = offers[0]["offerId"]

            policies = {
                k: v
                for k, v in {
                    "fulfillmentPolicyId": listing.shipping_policy_id,
                    "paymentPolicyId": listing.payment_policy_id,
                    "returnPolicyId": listing.return_policy_id,
                }.items()
                if v
            }
            offer_body = {
                "sku": sku,
                "marketplaceId": self.settings.ebay_marketplace_id,
                "format": "FIXED_PRICE",
                "availableQuantity": listing.quantity or 1,
                "categoryId": str(listing.category_id),
                "listingDescription": listing.description,
                "pricingSummary": {
                    "price": {"value": f"{float(listing.price):.2f}", "currency": "USD"}
                },
                **({"listingPolicies": policies} if policies else {}),
            }
            if offer_id is None:
                resp = await client.post(
                    f"{self.api_base}/sell/inventory/v1/offer", json=offer_body
                )
                if resp.status_code >= 400:
                    raise EbayPublishError(f"offer creation failed: {resp.text[:500]}")
                offer_id = resp.json()["offerId"]
            else:
                resp = await client.put(
                    f"{self.api_base}/sell/inventory/v1/offer/{offer_id}", json=offer_body
                )
                if resp.status_code >= 400:
                    raise EbayPublishError(f"offer update failed: {resp.text[:500]}")

            # 3. publish
            resp = await client.post(
                f"{self.api_base}/sell/inventory/v1/offer/{offer_id}/publish"
            )
            if resp.status_code >= 400:
                raise EbayPublishError(f"publish failed: {resp.text[:500]}")
            return resp.json()["listingId"]
