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
from app.routes.listings import router as listings_router
from app.routes.misc import (
    ebay_router,
    health_router,
    images_router,
    jobs_router,
    parts_router,
)

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.is_dev:
        # Dev convenience; production schema is managed by Alembic (alembic upgrade head).
        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield


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
    for router in (health_router, listings_router, jobs_router, parts_router, images_router, ebay_router):
        app.include_router(router, prefix="/api")

    dist = Path(REPO_ROOT) / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="spa")
    return app


app = create_app()
