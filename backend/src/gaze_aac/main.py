"""FastAPI uygulaması.

Çalıştırmak için:

    uvicorn gaze_aac.main:app --reload

Uygulama açılışında genişletici sağlayıcı bir kez kurulur ve
``app.state.expansion`` üstünde paylaşılır; model yükleme pahalı olduğundan
istek başına kurulmaz.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api.routes import expansion as expansion_routes
from .api.routes import health as health_routes
from .api.ws import router as ws_router
from .config import get_settings
from .nlp.expander import ExpansionService, build_provider
from .utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Açılış ve kapanışta bir kez çalışır."""
    settings = get_settings()
    setup_logging(settings.debug)

    provider = build_provider(settings.expander_provider, settings)
    app.state.expansion = ExpansionService(provider)

    logger.info(
        "Hazır | bakış kaynağı=%s | genişletici=%s | dwell=%d ms",
        settings.gaze_source,
        settings.expander_provider,
        settings.dwell_ms,
    )
    yield
    logger.info("Kapanıyor")


def create_app() -> FastAPI:
    """Uygulama fabrikası. Testler kendi örneğini bununla kurar."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Göz takibiyle Türkçe iletişim sistemi. Kısaltılmış girdiyi "
            "bağlam duyarlı dil modeliyle tam cümleye genişletir."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_routes.router)
    app.include_router(expansion_routes.router)
    app.include_router(ws_router)

    return app


app = create_app()
