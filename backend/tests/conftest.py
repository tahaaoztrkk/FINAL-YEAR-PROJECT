"""Ortak test yapılandırması."""

from __future__ import annotations

import os

import pytest

# Testler hiçbir zaman model indirmemeli: sağlayıcı sabitlenir.
os.environ.setdefault("EXPANDER_PROVIDER", "mock")
os.environ.setdefault("GAZE_SOURCE", "mouse")


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Ayarlar önbelleğe alınır; testler arasında temizlenir."""
    from gaze_aac.config import get_settings

    get_settings.cache_clear()
