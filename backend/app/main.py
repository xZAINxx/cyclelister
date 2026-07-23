"""CycleLister API — FastAPI application factory."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import REPO_ROOT, get_settings
from app.db.models import Base
from app.db.session import get_engine
from app.routes.analytics import router as analytics_router
from app.routes.history import router as history_router
from app.routes.listings import router as listings_router
from app.routes.misc import (
    digest_router,
    ebay_router,
    health_router,
    images_router,
    jobs_router,
    parts_router,
)

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    settings = get_settings()
    if settings.is_dev:
        # Dev convenience; production schema is managed by Alembic (alembic upgrade head).
        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    tasks: list[asyncio.Task] = []
    if settings.app_env != "test":
        if settings.ebay_client_id:
            tasks.append(asyncio.create_task(_order_poll_loop(settings.order_poll_minutes)))
        if settings.smtp_host and settings.digest_to:
            tasks.append(asyncio.create_task(_digest_loop()))
    yield
    for task in tasks:
        task.cancel()


async def _digest_loop() -> None:
    """Weekly summary email (spec §13): checks hourly, sends Monday mornings."""
    import asyncio
    import logging

    from app.db.session import get_session_factory
    from app.services.digest import digest_due, send_digest

    log = logging.getLogger("digest")
    while True:
        await asyncio.sleep(3600)
        try:
            async with get_session_factory()() as db:
                if await digest_due(db):
                    digest = await send_digest(db)
                    log.info("weekly digest sent (week of %s)", digest.week_start)
        except Exception:
            log.exception("digest loop failed")


async def _order_poll_loop(minutes: int) -> None:
    """Sale detection (spec §10): poll the Fulfillment API on a schedule."""
    import asyncio
    import logging

    from app.db.session import get_session_factory
    from app.services.ebay import EbayClient
    from app.services.sales import sync_ebay_orders

    log = logging.getLogger("order-poller")
    while True:
        await asyncio.sleep(minutes * 60)
        try:
            async with get_session_factory()() as db:
                if await EbayClient().connected(db):
                    result = await sync_ebay_orders(db)
                    if result["sales_archived"]:
                        log.info("archived %s sale(s)", result["sales_archived"])
        except Exception:  # never let the poller die (spec §15 resilience)
            log.exception("order poll failed")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="CycleLister API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in (health_router, listings_router, jobs_router, parts_router, images_router, ebay_router, analytics_router, history_router, digest_router):
        app.include_router(router, prefix="/api")

    dist = Path(REPO_ROOT) / "frontend" / "dist"
    if dist.exists():

        class SpaStaticFiles(StaticFiles):
            """Serve index.html for unknown non-API paths (client-side routing)."""

            async def get_response(self, path: str, scope):
                from starlette.exceptions import HTTPException as StarletteHTTPException

                try:
                    response = await super().get_response(path, scope)
                except StarletteHTTPException as exc:
                    if exc.status_code == 404 and "." not in path:
                        return await super().get_response("index.html", scope)
                    raise
                if response.status_code == 404 and "." not in path:
                    return await super().get_response("index.html", scope)
                return response

        app.mount("/", SpaStaticFiles(directory=dist, html=True), name="spa")
    return app


app = create_app()
