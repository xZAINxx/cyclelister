"""Dashboard analytics (spec §13, pulled forward): operations, sales, AI cost, inventory."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db.models import Fitment, Job, Listing, Part, SalesHistory, User
from app.db.session import get_db

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Sonnet-class standard pricing per million tokens (spec §8.4 cost observability).
INPUT_USD_PER_MTOK = 3.0
OUTPUT_USD_PER_MTOK = 15.0
STALE_DAYS = 90
WEEKS = 8


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _week_start(dt: datetime) -> str:
    dt = _aware(dt)
    monday = dt - timedelta(days=dt.weekday())
    return monday.date().isoformat()


def _week_buckets(now: datetime) -> list[str]:
    monday = now - timedelta(days=now.weekday())
    return [(monday - timedelta(weeks=i)).date().isoformat() for i in range(WEEKS - 1, -1, -1)]


@router.get("/summary")
async def summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    now = datetime.now(timezone.utc)
    d7, d30 = now - timedelta(days=7), now - timedelta(days=30)
    weeks = _week_buckets(now)
    window_start = now - timedelta(weeks=WEEKS)

    # --- operations -------------------------------------------------------------
    listings = (
        await db.execute(
            select(Listing.created_at, Listing.updated_at, Listing.status, Listing.ai_confidence, Listing.needs_human_review)
        )
    ).all()
    created_by_week: dict[str, int] = defaultdict(int)
    published_by_week: dict[str, int] = defaultdict(int)
    ops = {"created_7d": 0, "created_30d": 0, "published_7d": 0, "pending_review": 0, "draft": 0, "error": 0}
    confidences: list[float] = []
    review_flags = 0
    identified = 0
    for created_at, updated_at, status, ai_confidence, needs_review in listings:
        created_at = _aware(created_at)
        if created_at >= window_start:
            created_by_week[_week_start(created_at)] += 1
        if created_at >= d7:
            ops["created_7d"] += 1
        if created_at >= d30:
            ops["created_30d"] += 1
        if status == "listed":
            updated_at = _aware(updated_at)
            if updated_at >= d7:
                ops["published_7d"] += 1
            if updated_at >= window_start:
                published_by_week[_week_start(updated_at)] += 1
        if status == "pending_review":
            ops["pending_review"] += 1
        elif status == "draft":
            ops["draft"] += 1
        elif status == "error":
            ops["error"] += 1
        if ai_confidence is not None:
            identified += 1
            confidences.append(float(ai_confidence))
            if needs_review:
                review_flags += 1

    # --- sales (populates once eBay sale detection lands, Phase 3) ---------------
    sales = (
        await db.execute(select(SalesHistory.sold_date, SalesHistory.sold_price))
    ).all()
    sales_by_week_count: dict[str, int] = defaultdict(int)
    sales_by_week_rev: dict[str, float] = defaultdict(float)
    sales_30d = 0
    revenue_30d = 0.0
    prices = []
    for sold_date, sold_price in sales:
        if sold_date is None:
            continue
        sold_date = _aware(sold_date)
        price = float(sold_price or 0)
        prices.append(price)
        if sold_date >= d30:
            sales_30d += 1
            revenue_30d += price
        if sold_date >= window_start:
            wk = _week_start(sold_date)
            sales_by_week_count[wk] += 1
            sales_by_week_rev[wk] += price

    # --- AI cost from job usage logs ---------------------------------------------
    jobs = (
        await db.execute(select(Job.result, Job.created_at).where(Job.type == "listing_pipeline"))
    ).all()
    tokens_in = tokens_out = 0
    ai_runs_30d = 0
    cost_30d = 0.0
    for result, created_at in jobs:
        usage = (result or {}).get("ai_usage") or []
        job_in = sum(u.get("input_tokens", 0) for u in usage)
        job_out = sum(u.get("output_tokens", 0) for u in usage)
        tokens_in += job_in
        tokens_out += job_out
        job_cost = job_in / 1e6 * INPUT_USD_PER_MTOK + job_out / 1e6 * OUTPUT_USD_PER_MTOK
        if _aware(created_at) >= d30:
            ai_runs_30d += 1
            cost_30d += job_cost
    total_cost = tokens_in / 1e6 * INPUT_USD_PER_MTOK + tokens_out / 1e6 * OUTPUT_USD_PER_MTOK

    # --- inventory health ---------------------------------------------------------
    parts_total = (await db.execute(select(func.count(Part.id)))).scalar() or 0
    parts_with_fitment = (
        await db.execute(select(func.count(func.distinct(Fitment.part_id))))
    ).scalar() or 0
    fitment_rows = (await db.execute(select(func.count(Fitment.id)))).scalar() or 0
    stale_cutoff = now - timedelta(days=STALE_DAYS)
    stale = sum(
        1
        for created_at, _u, status, _c, _r in listings
        if status == "listed" and _aware(created_at) < stale_cutoff
    )
    active = sum(1 for _c, _u, status, _a, _r in listings if status == "listed")

    return {
        "operations": {
            **ops,
            "by_week": [
                {"week": w, "created": created_by_week.get(w, 0), "published": published_by_week.get(w, 0)}
                for w in weeks
            ],
        },
        "sales": {
            "sales_30d": sales_30d,
            "revenue_30d": round(revenue_30d, 2),
            "avg_price": round(sum(prices) / len(prices), 2) if prices else None,
            "total_sales": len(prices),
            "by_week": [
                {"week": w, "count": sales_by_week_count.get(w, 0), "revenue": round(sales_by_week_rev.get(w, 0), 2)}
                for w in weeks
            ],
            "connected": len(prices) > 0,  # true once sales exist (Phase 3 archival)
        },
        "ai": {
            "tokens_input": tokens_in,
            "tokens_output": tokens_out,
            "est_cost_total_usd": round(total_cost, 4),
            "est_cost_30d_usd": round(cost_30d, 4),
            "cost_per_listing_usd": round(total_cost / max(len(jobs), 1), 4),
            "avg_confidence": round(sum(confidences) / len(confidences), 3) if confidences else None,
            "review_rate": round(review_flags / identified, 3) if identified else None,
        },
        "inventory": {
            "parts_total": parts_total,
            "parts_with_fitment": parts_with_fitment,
            "fitment_coverage": round(parts_with_fitment / parts_total, 3) if parts_total else 0,
            "fitment_rows": fitment_rows,
            "active_listings": active,
            "stale_listings": stale,
            "stale_threshold_days": STALE_DAYS,
        },
    }
