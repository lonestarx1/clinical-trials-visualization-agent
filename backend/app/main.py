import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import debug, health
from app.api.errors import install_error_handlers
from app.core.config import Settings
from app.core.logging import configure_logging
from app.core.pricing import load_pricing, missing_prices
from app.ctgov.client import CtgovClient, RateLimiter
from app.store.db import create_engine

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        for model in sorted(missing_prices(settings, load_pricing())):
            log.warning("no price for model %s: its cost will be recorded as unknown", model)
        app.state.engine = create_engine(settings.database_url)
        http = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0))
        app.state.ctgov = CtgovClient(
            settings.ctgov_base_url,
            http,
            RateLimiter(settings.ctgov_rate_limit_per_min, settings.ctgov_max_concurrency),
        )
        log.info("api started")
        yield
        await http.aclose()
        await app.state.engine.dispose()

    app = FastAPI(
        title="ClinicalTrials.gov Query-to-Visualization Agent",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(health.router)
    if settings.enable_debug_endpoints:
        app.include_router(debug.router)
    install_error_handlers(app)
    return app
