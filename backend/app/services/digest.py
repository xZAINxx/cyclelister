"""Weekly summary digest (spec §13): simple, chart-free, non-technical email.

- build_weekly_digest: aggregates the week from real tables.
- render_digest_html: self-contained inline-styled email (Paddock palette).
- send_digest: SMTP when configured, else raises DigestNotConfiguredError —
  the preview endpoint works either way.
- A `jobs` row (type=weekly_digest) records each send so the scheduler
  never double-sends within a week.
"""
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import Job, Listing, Part, SalesHistory


class DigestNotConfiguredError(RuntimeError):
    pass


@dataclass
class Digest:
    week_start: str
    listings_created: int
    listings_published: int
    pending_review: int
    sales_count: int
    revenue: float
    avg_sale: float | None
    top_sales: list[dict]
    catalog_total: int
    stale_count: int


async def build_weekly_digest(db: AsyncSession) -> Digest:
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    def _aware(dt):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    listings = (
        await db.execute(select(Listing.created_at, Listing.updated_at, Listing.status, Listing.quantity))
    ).all()
    created = sum(1 for c, _u, _s, _q in listings if _aware(c) >= week_ago)
    published = sum(
        1 for _c, u, s, _q in listings if s in ("listed", "sold") and _aware(u) >= week_ago
    )
    pending = sum(1 for _c, _u, s, _q in listings if s == "pending_review")
    stale_cutoff = now - timedelta(days=90)
    stale = sum(
        1 for c, _u, s, q in listings if s == "listed" and (_aware(c) < stale_cutoff or q <= 0)
    )

    sales_rows = (
        await db.execute(
            select(SalesHistory)
            .where(SalesHistory.sold_date >= week_ago)
            .order_by(SalesHistory.sold_price.desc())
        )
    ).scalars().all()
    prices = [float(r.sold_price) for r in sales_rows if r.sold_price is not None]

    catalog_total = (await db.execute(select(func.count(Part.id)))).scalar() or 0

    return Digest(
        week_start=week_ago.date().isoformat(),
        listings_created=created,
        listings_published=published,
        pending_review=pending,
        sales_count=len(sales_rows),
        revenue=round(sum(prices), 2),
        avg_sale=round(sum(prices) / len(prices), 2) if prices else None,
        top_sales=[
            {"title": r.title or "(untitled)", "price": float(r.sold_price or 0)}
            for r in sales_rows[:5]
        ],
        catalog_total=catalog_total,
        stale_count=stale,
    )


def render_digest_html(d: Digest) -> str:
    def stat(label: str, value: str, sub: str = "") -> str:
        return (
            f'<td style="background:#1e2024;border:1px solid #2a2d33;border-radius:4px;'
            f'padding:14px;vertical-align:top">'
            f'<div style="color:#8a8f98;font-size:11px;letter-spacing:.12em;'
            f'text-transform:uppercase">{label}</div>'
            f'<div style="color:#ffffff;font-size:26px;font-weight:800">{value}</div>'
            f'<div style="color:#8a8f98;font-size:12px">{sub}</div></td>'
        )

    top_rows = "".join(
        f'<tr><td style="padding:6px 8px;color:#e9ebee;font-size:13px;'
        f'border-bottom:1px solid #2a2d33">{s["title"][:70]}</td>'
        f'<td style="padding:6px 8px;color:#ffd400;font-family:monospace;'
        f'border-bottom:1px solid #2a2d33;text-align:right">${s["price"]:.2f}</td></tr>'
        for s in d.top_sales
    ) or '<tr><td style="padding:8px;color:#8a8f98;font-size:13px">No sales this week.</td></tr>'

    stale_note = (
        f'<p style="color:#ffd400;font-size:13px">&#9888; {d.stale_count} listing(s) need '
        f"attention (stale or out of stock) — see the dashboard action list.</p>"
        if d.stale_count
        else ""
    )

    return f"""<!doctype html><html><body style="margin:0;background:#0e0e10;padding:24px;font-family:Arial,Helvetica,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;margin:0 auto">
<tr><td style="padding-bottom:14px">
  <span style="color:#ffffff;font-size:20px;font-weight:900;letter-spacing:.02em">CYCLE<span style="color:#ffd400">LISTER</span></span>
  <span style="color:#8a8f98;font-size:12px"> &nbsp;weekly summary &middot; week of {d.week_start}</span>
</td></tr>
<tr><td>
<table width="100%" cellpadding="0" cellspacing="8"><tr>
{stat("Listings created", str(d.listings_created), f"{d.listings_published} published")}
{stat("Sales", str(d.sales_count), f"avg ${d.avg_sale:.2f}" if d.avg_sale else "")}
{stat("Revenue", f"${d.revenue:,.2f}", "")}
</tr><tr>
{stat("Awaiting review", str(d.pending_review), "drafts ready for you")}
{stat("Catalog", f"{d.catalog_total:,}", "known parts")}
{stat("Needs attention", str(d.stale_count), "stale / out of stock")}
</tr></table>
</td></tr>
<tr><td style="padding-top:12px">
  <div style="color:#8a8f98;font-size:11px;letter-spacing:.12em;text-transform:uppercase;padding-bottom:6px">Top sales this week</div>
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#1e2024;border:1px solid #2a2d33;border-radius:4px">{top_rows}</table>
  {stale_note}
</td></tr>
</table></body></html>"""


async def send_digest(db: AsyncSession, settings: Settings | None = None) -> Digest:
    settings = settings or get_settings()
    if not (settings.smtp_host and settings.digest_to):
        raise DigestNotConfiguredError(
            "Email is not configured. Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, "
            "DIGEST_FROM and DIGEST_TO in the backend environment."
        )
    digest = await build_weekly_digest(db)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"CycleLister weekly summary — week of {digest.week_start}"
    msg["From"] = settings.digest_from or settings.smtp_user
    msg["To"] = settings.digest_to
    msg.attach(
        MIMEText(
            f"Listings created: {digest.listings_created}\nSales: {digest.sales_count}\n"
            f"Revenue: ${digest.revenue:,.2f}\nAwaiting review: {digest.pending_review}",
            "plain",
        )
    )
    msg.attach(MIMEText(render_digest_html(digest), "html"))

    import asyncio

    def _send():
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)

    await asyncio.to_thread(_send)
    db.add(Job(type="weekly_digest", status="succeeded", result={"week": digest.week_start}))
    await db.commit()
    return digest


async def digest_due(db: AsyncSession) -> bool:
    """Monday, and no digest sent in the last 6 days."""
    now = datetime.now(timezone.utc)
    if now.weekday() != 0:
        return False
    last = (
        await db.execute(
            select(Job)
            .where(Job.type == "weekly_digest", Job.status == "succeeded")
            .order_by(Job.created_at.desc())
        )
    ).scalars().first()
    if last is None:
        return True
    last_at = last.created_at if last.created_at.tzinfo else last.created_at.replace(tzinfo=timezone.utc)
    return last_at < now - timedelta(days=6)
