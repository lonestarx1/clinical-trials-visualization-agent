from fastapi import Request
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.pricing import Pricing
from app.ctgov.client import CtgovClient
from app.llm.client import OpenAILLM, UsageLog
from app.pipeline.query import LLMFactory, StageLLMs


def get_ctgov(request: Request) -> CtgovClient:
    client: CtgovClient = request.app.state.ctgov
    return client


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_sessions(request: Request) -> async_sessionmaker[AsyncSession] | None:
    """None when the app runs without a database (offline tests)."""
    return getattr(request.app.state, "sessions", None)


def openai_factory(client: AsyncOpenAI, settings: Settings, pricing: Pricing) -> LLMFactory:
    """Builds the three stage models for one request, sharing one usage log."""

    def build(usage: UsageLog) -> StageLLMs:
        def stage(name: str) -> OpenAILLM:
            return OpenAILLM(
                client, getattr(settings, name), stage=name, pricing=pricing, usage=usage
            )

        return StageLLMs(stage("guard"), stage("planner"), stage("narrator"))

    return build


def get_llm_factory(request: Request) -> LLMFactory:
    factory: LLMFactory = request.app.state.llm_factory
    return factory


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:  # behind the reverse proxy (Caddy)
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
