import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api import debug, health, query, results
from app.api.deps import openai_factory
from app.api.errors import install_error_handlers
from app.api.openapi import DESCRIPTION, SERVERS, TAGS, install_openapi
from app.api.ratelimit import RateLimitMiddleware
from app.core.config import Settings
from app.core.logging import configure_logging
from app.core.pricing import load_pricing, missing_prices
from app.ctgov.client import CtgovClient, RateLimiter
from app.store.db import create_engine
from app.store.results import CODE_VERSION
from app.workers.runner import requeue_stale, worker_loop

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.pricing = load_pricing()
        for model in sorted(missing_prices(settings, app.state.pricing)):
            log.warning("no price for model %s: its cost will be recorded as unknown", model)
        app.state.engine = create_engine(settings.database_url)
        app.state.sessions = async_sessionmaker(app.state.engine, expire_on_commit=False)
        app.state.openai = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
        app.state.llm_factory = openai_factory(app.state.openai, settings, app.state.pricing)
        http = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0))
        app.state.ctgov = CtgovClient(
            settings.ctgov_base_url,
            http,
            RateLimiter(
                settings.ctgov_rate_limit_per_min,
                settings.ctgov_max_concurrency,
                burst=settings.ctgov_rate_burst,
            ),
            count_ttl=settings.ctgov_count_cache_seconds,
        )
        workers: list[asyncio.Task[None]] = []
        try:
            await requeue_stale(app)
            workers = [
                asyncio.create_task(worker_loop(app, i)) for i in range(settings.job_workers)
            ]
        except Exception:  # the API still serves synchronous questions without workers
            log.exception("background workers not started (database unavailable?)")
        log.info("api started with %d background workers", len(workers))
        yield
        for task in workers:
            task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        await http.aclose()
        await app.state.openai.close()
        await app.state.engine.dispose()

    app = FastAPI(
        title="ClinicalTrials.gov Query-to-Visualization Agent",
        version=CODE_VERSION,
        summary="Ask about clinical trials, get a cited chart specification.",
        description=DESCRIPTION,
        servers=SERVERS,
        openapi_tags=TAGS,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_ip_per_min)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.include_router(health.router)
    app.include_router(query.router)
    app.include_router(results.router)
    if settings.enable_debug_endpoints:
        app.include_router(debug.router)
    install_error_handlers(app)
    install_openapi(app)
    return app
