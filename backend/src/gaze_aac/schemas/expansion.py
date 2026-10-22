"""Kısaltma genişletmesiyle ilgili şemalar."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Candidate(BaseModel):
    """Bir kısaltmaya karşılık üretilen aday cümle."""

    model_config = ConfigDict(extra="forbid")

    text: str
    score: float = Field(
        default=0.0, description="Sağlayıcının güven puanı; karşılaştırma için sıralama anahtarı"
    )
    valid: bool = Field(
        default=True,
        description="Adayın kısaltması girdiyle eşleşiyor mu (geri kontrol sonucu)",
    )


class ExpansionRequest(BaseModel):
    """Genişletici sağlayıcısına giden istek."""

    model_config = ConfigDict(extra="forbid")

    abbreviation: str = Field(min_length=1)
    scheme: str = "S1"
    context: str | None = None
    top_k: int = Field(default=5, ge=1, le=10)


class ExpansionResult(BaseModel):
    """Sağlayıcıdan dönen sonuç."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[Candidate]
    provider: str
    latency_ms: float
    model_id: str | None = None
