from fastapi import Request

from app.core.config import Settings
from app.ctgov.client import CtgovClient


def get_ctgov(request: Request) -> CtgovClient:
    client: CtgovClient = request.app.state.ctgov
    return client


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings
