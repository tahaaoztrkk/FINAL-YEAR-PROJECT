"""Uygulama yapılandırması.

Tüm ayarlar ortam değişkeninden okunur; kodun içine sabit değer yazılmaz.
Yerel geliştirmede ``.env`` dosyası kullanılır (``.env.example`` kopyalanarak).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

GazeSource = Literal["mouse", "webcam"]
ExpanderProvider = Literal["mock", "ngram", "hf_local", "openai_compatible"]

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Göz Takibiyle Türkçe İletişim"
    debug: bool = True
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # Bakış hattı
    gaze_source: GazeSource = "mouse"
    smoothing_window: int = Field(default=5, ge=1, le=30)

    # Dwell
    dwell_ms: int = Field(default=700, ge=200, le=3000)
    dwell_cancel_ms: int = Field(
        default=150,
        ge=0,
        description="Bakış hedeften ayrıldıktan sonra ilerlemenin korunduğu süre",
    )

    # Kalibrasyon
    calibration_points: int = Field(default=9, ge=4, le=25)
    calibration_hold_ms: int = 1200
    calibration_discard_ms: int = 300
    screen_distance_cm: float = Field(
        default=60.0, description="Göz–ekran mesafesi; dereceye çevirmede kullanılır"
    )
    screen_width_cm: float = Field(default=34.5, description="Ekranın fiziksel genişliği")

    # Genişletici
    expander_provider: ExpanderProvider = "mock"
    expander_top_k: int = Field(default=5, ge=1, le=10)
    expander_timeout_s: float = 2.0

    hf_model_id: str = "ytu-ce-cosmos/Turkish-Gemma-9b-v0.1"
    hf_load_in_4bit: bool = True
    hf_adapter_path: str = ""

    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    data_dir: Path = _BACKEND_ROOT.parent / "data"

    @property
    def corpus_path(self) -> Path:
        return self.data_dir / "processed" / "aac_corpus.jsonl"

    @property
    def pairs_path(self) -> Path:
        return self.data_dir / "processed" / "training_pairs.jsonl"


@lru_cache
def get_settings() -> Settings:
    """Tek örnek ayar nesnesi. FastAPI bağımlılığı olarak da kullanılır."""
    return Settings()
