"""Smart Pricing engine (spec §7) — business-critical module.

Contracts honored:
- §7.1 provider abstraction: Browse API (active comps, primary) · Marketplace
  Insights (sold, feature-flagged, off until eBay grants access) · internal
  sales_history (own sold prices, strong signal for recurring NOS).
- §7.2 undercut: reference = lowest legitimate comp after outlier filtering;
  undercut clamped 5-10 (default 8); floor always wins; thin markets never
  get blind undercuts — they get a suggestion + needs_human_review.
- §7.3 rounding: round_to_95 = largest k.95 <= x (never round up past the
  competitor), minimum 0.95. When the FLOOR binds we round UP to the nearest
  .95 instead — the spec's "never price below the floor" rule outranks the
  never-round-up bias (§17 open question, resolved conservatively).
- §7.4 volume tiers: undercut applies to the qty-1 base price. Publishing
  eBay Volume Pricing awaits the seller's tier data (Phase 2.x).
- §7.5 free shipping: threshold from pricing_rules, noted in the explanation.
- price_source always recorded on the listing (§7.1 transparency).
"""
import re
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_FLOOR
from statistics import median

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import Listing, Part, PricingRule, SalesHistory
from app.services.catalog import normalize_part_number

MIN_COMPS = 3  # spec §7.2: thin/no competition is common for NOS, not rare

CENT = Decimal("0.01")
NINETY_FIVE = Decimal("0.95")

# titles that are not comparable to a single part (spec §7.2 outlier filter)
_BUNDLE_RE = re.compile(r"\b(lot of|bulk lot|job lot|wholesale|bundle|assortment)\b", re.I)


# ---------------------------------------------------------------- rounding --
def round_to_95(x: float | Decimal) -> Decimal:
    """Largest value of form k.95 that is <= x; 0.95 when x < 0.95 (spec §7.3)."""
    x = Decimal(str(x))
    if x < NINETY_FIVE:
        return NINETY_FIVE
    whole = (x - NINETY_FIVE).quantize(Decimal("1"), rounding=ROUND_FLOOR)
    return (whole + NINETY_FIVE).quantize(CENT)


def round_up_to_95(x: float | Decimal) -> Decimal:
    """Smallest k.95 >= x — used only when the floor binds (never violate it)."""
    x = Decimal(str(x))
    candidate = round_to_95(x)
    if candidate < x:
        candidate += Decimal("1")
    return candidate.quantize(CENT)


# ------------------------------------------------------------------- comps --
@dataclass
class Comp:
    price: Decimal
    title: str
    source: str
    condition: str | None = None
    item_id: str | None = None


def filter_comps(comps: list[Comp], part_number: str | None, keywords: str) -> list[Comp]:
    """Keep comps honest: part-number match or title-keyword overlap; no bundles."""
    normalized_pn = normalize_part_number(part_number or "")
    kw_tokens = {t for t in re.split(r"\W+", keywords.lower()) if len(t) > 2}
    kept: list[Comp] = []
    for comp in comps:
        if comp.price is None or comp.price <= 0:
            continue
        if _BUNDLE_RE.search(comp.title):
            continue
        title_norm = normalize_part_number(comp.title)
        if normalized_pn and normalized_pn in title_norm:
            kept.append(comp)
            continue
        title_tokens = {t for t in re.split(r"\W+", comp.title.lower()) if len(t) > 2}
        overlap = len(kw_tokens & title_tokens)
        if kw_tokens and overlap / max(len(kw_tokens), 1) >= 0.5:
            kept.append(comp)
    return kept


def choose_reference_price(comps: list[Comp]) -> Decimal:
    """Lowest legitimate competitor (spec §7.2); comps must be pre-filtered."""
    return min(c.price for c in comps)


# ----------------------------------------------------------------- sources --
class BrowseApiSource:
    """eBay Browse API — active listings, the primary allowed source (§7.1)."""

    _token: str | None = None

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def available(self) -> bool:
        return bool(self.settings.ebay_client_id and self.settings.ebay_client_secret)

    @property
    def _api_base(self) -> str:
        return (
            "https://api.sandbox.ebay.com"
            if self.settings.ebay_env == "sandbox"
            else "https://api.ebay.com"
        )

    async def _app_token(self) -> str:
        import base64

        raw = f"{self.settings.ebay_client_id}:{self.settings.ebay_client_secret}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._api_base}/identity/v1/oauth2/token",
                headers={
                    "Authorization": f"Basic {base64.b64encode(raw.encode()).decode()}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "client_credentials",
                    "scope": "https://api.ebay.com/oauth/api_scope",
                },
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

    async def get_active_comps(
        self, part_number: str | None, keywords: str, category: str | None
    ) -> list[Comp]:
        if not self.available:
            return []
        token = await self._app_token()
        params = {"q": part_number or keywords, "limit": "50"}
        if category:
            params["category_ids"] = category
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self._api_base}/buy/browse/v1/item_summary/search",
                params=params,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-EBAY-C-MARKETPLACE-ID": self.settings.ebay_marketplace_id,
                },
            )
            resp.raise_for_status()
            items = resp.json().get("itemSummaries") or []
        comps = []
        for item in items:
            value = (item.get("price") or {}).get("value")
            if value is None:
                continue
            comps.append(
                Comp(
                    price=Decimal(str(value)),
                    title=item.get("title") or "",
                    condition=item.get("condition"),
                    item_id=item.get("itemId"),
                    source="ebay_browse",
                )
            )
        return comps


class InternalHistorySource:
    """The seller's own sales_history — real sold prices (§7.1 source 3)."""

    async def get_sold_comps(self, db: AsyncSession, part_number: str | None) -> list[Comp]:
        normalized = normalize_part_number(part_number or "")
        if not normalized:
            return []
        rows = (
            await db.execute(
                select(SalesHistory)
                .where(SalesHistory.part_number == normalized)
                .where(SalesHistory.sold_price.is_not(None))
                .order_by(SalesHistory.sold_date.desc())
                .limit(10)
            )
        ).scalars().all()
        return [
            Comp(price=Decimal(str(r.sold_price)), title=r.title or "", source="internal_history")
            for r in rows
        ]


class InsightsSource:
    """eBay Marketplace Insights — sold data, gated on account approval (§7.1)."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def available(self) -> bool:
        return self.settings.ebay_insights_enabled and bool(self.settings.ebay_client_id)

    async def get_sold_comps(self, part_number, keywords, category) -> list[Comp]:
        # Implemented when the client's account is granted Insights access.
        return []


# ------------------------------------------------------------------- rules --
@dataclass
class RuleSet:
    undercut_pct: Decimal = Decimal("8")
    floor: Decimal | None = None
    free_shipping_threshold: Decimal | None = None
    min_comps: int = MIN_COMPS


def _clamp_undercut(rule: PricingRule) -> Decimal:
    lo = Decimal(str(rule.undercut_pct_min or 5))
    hi = Decimal(str(rule.undercut_pct_max or 10))
    lo = max(lo, Decimal("5"))
    hi = min(hi, Decimal("10"))
    mid = (lo + hi) / 2
    return mid.quantize(CENT)


async def resolve_rules(
    db: AsyncSession, category_id: str | None, part_id
) -> RuleSet:
    """Most specific wins: part scope > category scope > global > code defaults."""
    rules = (await db.execute(select(PricingRule))).scalars().all()
    chosen: PricingRule | None = None
    for scope, ref in (("part", str(part_id) if part_id else None), ("category", category_id), ("global", None)):
        for rule in rules:
            if rule.scope == scope and (scope == "global" or rule.scope_ref == ref):
                chosen = rule
                break
        if chosen:
            break
    if chosen is None:
        return RuleSet()
    return RuleSet(
        undercut_pct=_clamp_undercut(chosen),
        floor=Decimal(str(chosen.floor_absolute)) if chosen.floor_absolute is not None else None,
        free_shipping_threshold=(
            Decimal(str(chosen.free_shipping_threshold))
            if chosen.free_shipping_threshold is not None
            else None
        ),
    )


# ------------------------------------------------------------------ engine --
@dataclass
class PricingResult:
    price: Decimal | None
    computed_competitor_price: Decimal | None
    undercut_pct: Decimal | None
    price_source: str
    explanation: str
    needs_review: bool
    comps_considered: int = 0
    extras: dict = field(default_factory=dict)


def _apply_floor(target: Decimal, rules: RuleSet) -> tuple[Decimal, bool]:
    price = round_to_95(target)
    if rules.floor is not None and price < rules.floor:
        return round_up_to_95(rules.floor), True
    return price, False


def _free_ship_note(price: Decimal, rules: RuleSet) -> str:
    if rules.free_shipping_threshold is not None and price >= rules.free_shipping_threshold:
        return " · qualifies for free shipping"
    return ""


async def price_listing(
    db: AsyncSession,
    listing: Listing,
    *,
    browse: BrowseApiSource | None = None,
    history: InternalHistorySource | None = None,
) -> PricingResult:
    browse = browse or BrowseApiSource()
    history = history or InternalHistorySource()

    part: Part | None = None
    if listing.part_id is not None:
        part = await db.get(Part, listing.part_id)
    part_number = part.part_number_display if part else None
    keywords = " ".join(
        filter(None, [part.brand if part else None, part.part_type if part else None])
    ) or (listing.title or listing.hint or "")

    rules = await resolve_rules(db, listing.category_id, listing.part_id)

    # Sold signal first (spec §7.1: prefer sold data when present).
    sold = await history.get_sold_comps(db, part_number)
    if len(sold) >= 1:
        ref = Decimal(str(median(c.price for c in sold))).quantize(CENT)
        # Own sold prices are proven willingness-to-pay — match, don't undercut.
        price, floored = _apply_floor(ref, rules)
        confident = len(sold) >= rules.min_comps
        note = f"matches your sold-history median ${ref} ({len(sold)} sale{'s' if len(sold) != 1 else ''})"
        if floored:
            note += f"; floor ${rules.floor} applied"
        return PricingResult(
            price=price,
            computed_competitor_price=ref,
            undercut_pct=Decimal("0"),
            price_source="internal_history",
            explanation=f"${price} — {note}{_free_ship_note(price, rules)}",
            needs_review=not confident,
            comps_considered=len(sold),
        )

    # Active competition via Browse API (§7.2).
    active_raw = await browse.get_active_comps(part_number, keywords, listing.category_id)
    active = filter_comps(active_raw, part_number, keywords or (listing.title or ""))

    if len(active) >= rules.min_comps:
        reference = choose_reference_price(active)
        target = reference * (Decimal("1") - rules.undercut_pct / Decimal("100"))
        price, floored = _apply_floor(target, rules)
        if floored:
            explanation = (
                f"${price} — floor ${rules.floor} applied; {rules.undercut_pct}% below "
                f"lowest competitor ${reference} would have been ${round_to_95(target)}"
            )
        else:
            explanation = (
                f"${price} — {rules.undercut_pct}% below lowest competitor ${reference} "
                f"({len(active)} comps via eBay Browse)"
            )
        return PricingResult(
            price=price,
            computed_competitor_price=reference,
            undercut_pct=rules.undercut_pct,
            price_source="ebay_browse",
            explanation=explanation + _free_ship_note(price, rules),
            needs_review=floored,
            comps_considered=len(active),
        )

    if active:  # thin market — suggest, never undercut blindly (§7.2)
        reference = choose_reference_price(active)
        price, _ = _apply_floor(reference, rules)
        return PricingResult(
            price=price,
            computed_competitor_price=reference,
            undercut_pct=Decimal("0"),
            price_source="ebay_browse_thin",
            explanation=(
                f"Suggested ${price} — only {len(active)} comparable "
                f"listing{'s' if len(active) != 1 else ''} found; review price"
            ),
            needs_review=True,
            comps_considered=len(active),
        )

    return PricingResult(
        price=None,
        computed_competitor_price=None,
        undercut_pct=None,
        price_source="none" if browse.available else "unavailable",
        explanation=(
            "No comparable listings found — set price manually"
            if browse.available
            else "Pricing sources unavailable (eBay not configured) and no sold history — set price manually"
        ),
        needs_review=True,
        comps_considered=0,
    )


async def apply_pricing(db: AsyncSession, listing: Listing, result: PricingResult) -> None:
    """Persist a pricing result onto the listing (price_source per §7.1)."""
    if result.price is not None:
        listing.price = result.price
    listing.computed_competitor_price = result.computed_competitor_price
    listing.undercut_pct = result.undercut_pct
    listing.price_source = result.price_source
    listing.price_explanation = result.explanation
    if result.needs_review:
        listing.needs_human_review = True
    await db.commit()
