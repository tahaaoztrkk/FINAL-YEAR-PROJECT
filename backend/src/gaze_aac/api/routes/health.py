"""Sağlık ve yapılandırma uç noktaları."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...config import Settings, get_settings
from ...nlp.schemes import all_schemes

router = APIRouter(tags=["sistem"])


class HealthResponse(BaseModel):
    status: str
    version: str
    gaze_source: str
    expander_provider: str


class SchemeInfo(BaseModel):
    id: str
    name: str
    description: str


@router.get("/health", response_model=HealthResponse)
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    """Servisin ayakta olduğunu ve hangi bileşenlerle çalıştığını bildirir."""
    from ... import __version__

    return HealthResponse(
        status="ok",
        version=__version__,
        gaze_source=settings.gaze_source,
        expander_provider=settings.expander_provider,
    )


@router.get("/schemes", response_model=list[SchemeInfo])
def schemes() -> list[SchemeInfo]:
    """Tanımlı kısaltma şemaları. Arayüz seçim menüsünü bununla doldurur."""
    return [SchemeInfo(id=s.id, name=s.name, description=s.description) for s in all_schemes()]
