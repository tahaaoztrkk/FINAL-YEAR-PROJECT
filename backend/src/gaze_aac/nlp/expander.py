"""Kısaltmayı cümleye genişleten sağlayıcı arayüzü.

Sağlayıcılar takılıp çıkarılabilir: geliştirmede ``mock``, taban çizgisi
ölçümünde ``ngram``, asıl sistemde ``hf_local``, üst sınır karşılaştırmasında
``openai_compatible``. Hepsi aynı protokolü uygular, bu yüzden simülasyon ve
API kodu hangisinin çalıştığını bilmek zorunda değildir.

Geri kontrol (back-check) burada, sağlayıcıdan bağımsız olarak uygulanır:
üretilen cümlenin kısaltması girdiyle eşleşmiyorsa aday geçersiz işaretlenir.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..schemas.expansion import Candidate, ExpansionRequest, ExpansionResult
from .schemes import get_scheme


@runtime_checkable
class ExpansionProvider(Protocol):
    """Bir kısaltmaya karşılık aday cümleler üreten bileşen."""

    name: str

    async def expand(self, request: ExpansionRequest) -> list[Candidate]:
        """Aday cümleleri üretir. Sıralama güven puanına göre yapılır."""
        ...


def back_check(candidates: list[Candidate], request: ExpansionRequest) -> list[Candidate]:
    """Adayların kısaltmasını yeniden hesaplayıp girdiyle karşılaştırır.

    Eşleşmeyen aday atılmaz, ``valid=False`` işaretlenir: arayüz bunları
    göstermez ama değerlendirme sırasında modelin ne kadar saptığını ölçmek
    için kayıtta kalmaları gerekir.
    """
    scheme = get_scheme(request.scheme)
    return [
        candidate.model_copy(update={"valid": scheme.matches(candidate.text, request.abbreviation)})
        for candidate in candidates
    ]


class ExpansionService:
    """Sağlayıcıyı çağırır, geri kontrolü uygular, süreyi ölçer."""

    def __init__(self, provider: ExpansionProvider) -> None:
        self._provider = provider

    @property
    def provider_name(self) -> str:
        return self._provider.name

    async def expand(self, request: ExpansionRequest) -> ExpansionResult:
        """Kısaltmayı genişletir ve doğrulanmış adayları döner."""
        started = time.perf_counter()
        raw = await self._provider.expand(request)
        checked = back_check(raw, request)

        # Geçerli adaylar öne, kendi içlerinde puana göre sıralanır.
        ordered = sorted(checked, key=lambda c: (not c.valid, -c.score))

        return ExpansionResult(
            candidates=ordered[: request.top_k],
            provider=self._provider.name,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            model_id=getattr(self._provider, "model_id", None),
        )


def default_corpus_path(settings: object) -> Path | None:
    """Derlem tabanlı sağlayıcıların okuyacağı dosya.

    İşlenmiş derlem varsa o, yoksa repodaki ham derlem kullanılır; böylece
    ``build_corpus`` hiç çalıştırılmamış bir klonda da ``ngram`` aday üretir.
    """
    for name in ("corpus_path", "source_corpus_path"):
        path = getattr(settings, name, None)
        if isinstance(path, Path) and path.exists():
            return path
    return None


def build_provider(
    provider_name: str, settings: object, corpus_path: Path | None = None
) -> ExpansionProvider:
    """Ayarlara göre sağlayıcı örneği üretir.

    ``corpus_path`` yalnızca derlem tabanlı sağlayıcılar (mock, ngram) için
    anlamlıdır. Simülasyon buraya eğitim kümesini verir: değerlendirme
    cümlelerini gören bir n-gram modelinin sonucu ölçüm değil ezberdir.

    İçe aktarmalar işlev içinde yapılır: ``torch`` ve ``transformers`` ağır
    paketlerdir, ``mock`` sağlayıcıyla çalışan bir geliştiricinin bunları
    kurmuş olması gerekmez.

    Raises:
        ValueError: Bilinmeyen sağlayıcı adı.
    """
    if provider_name == "mock":
        from .providers.mock import MockProvider

        return MockProvider(corpus_path or default_corpus_path(settings))

    if provider_name == "ngram":
        from .providers.ngram import NGramProvider

        return NGramProvider(corpus_path or default_corpus_path(settings))

    if provider_name == "hf_local":
        from .providers.hf_local import HuggingFaceProvider

        return HuggingFaceProvider(
            model_id=getattr(settings, "hf_model_id", ""),
            load_in_4bit=getattr(settings, "hf_load_in_4bit", True),
            adapter_path=getattr(settings, "hf_adapter_path", "") or None,
        )

    if provider_name == "openai_compatible":
        from .providers.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(
            base_url=getattr(settings, "llm_base_url", ""),
            api_key=getattr(settings, "llm_api_key", ""),
            model=getattr(settings, "llm_model", ""),
        )

    raise ValueError(
        f"Bilinmeyen genişletici sağlayıcı: {provider_name!r}. "
        "Seçenekler: mock, ngram, hf_local, openai_compatible"
    )
