from fastapi import Request
from openai import AsyncOpenAI

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


def get_llm_factory(request: Request) -> LLMFactory:
    """Builds the three stage models for one request, sharing one usage log."""
    client: AsyncOpenAI = request.app.state.openai
    settings: Settings = request.app.state.settings
    pricing: Pricing = request.app.state.pricing

    def build(usage: UsageLog) -> StageLLMs:
        def stage(name: str) -> OpenAILLM:
            return OpenAILLM(
                client, getattr(settings, name), stage=name, pricing=pricing, usage=usage
            )

        return StageLLMs(stage("guard"), stage("planner"), stage("narrator"))

    return build
