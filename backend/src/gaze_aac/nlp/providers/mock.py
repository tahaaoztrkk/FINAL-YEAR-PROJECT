"""Model gerektirmeyen sahte sağlayıcı.

Derlemdeki cümleler arasından kısaltmaya uyanları döner. Amacı arayüz ve
entegrasyon geliştirmesini modelden bağımsız kılmak: Kişi 3, dil modeli hazır
olmadan uçtan uca akışı çalıştırabilir.

Derlem yoksa gömülü küçük bir cümle listesi kullanılır, böylece depo klonlanıp
``uvicorn`` çalıştırıldığında sistem ilk dakikada çalışır.
"""

from __future__ import annotations

from pathlib import Path

from ...schemas.expansion import Candidate, ExpansionRequest
from ..schemes import get_scheme, normalize_abbreviation

FALLBACK_SENTENCES: tuple[str, ...] = (
    "Su istiyorum.",
    "Acım var.",
    "Başım ağrıyor.",
    "Biraz dinlenmek istiyorum.",
    "Pozisyonumu değiştirir misin?",
    "Teşekkür ederim.",
    "Hayır, istemiyorum.",
    "Evet, lütfen.",
    "Doktoru çağırır mısın?",
    "Televizyonu açar mısın?",
    "Yarın hastaneye gitmek istemiyorum.",
    "Annemle konuşmak istiyorum.",
    "Üşüyorum, battaniye alır mısın?",
    "Bugün kendimi iyi hissediyorum.",
    "Biraz müzik dinlemek istiyorum.",
    "Yatağımı yukarı kaldırır mısın?",
    "Ağzım kurudu.",
    "Nefes almakta zorlanıyorum.",
    "Seni özledim.",
    "Ne zaman geleceksin?",
)


class MockProvider:
    """Derlemden kural tabanlı eşleştirme yapan sağlayıcı."""

    name = "mock"

    def __init__(self, corpus_path: Path | None = None) -> None:
        self._sentences = self._load(corpus_path)

    @staticmethod
    def _load(corpus_path: Path | None) -> list[str]:
        if corpus_path is None or not corpus_path.exists():
            return list(FALLBACK_SENTENCES)

        import json

        sentences: list[str] = []
        with corpus_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = record.get("text") if isinstance(record, dict) else None
                if isinstance(text, str) and text:
                    sentences.append(text)
        return sentences or list(FALLBACK_SENTENCES)

    async def expand(self, request: ExpansionRequest) -> list[Candidate]:
        scheme = get_scheme(request.scheme)
        wanted = normalize_abbreviation(request.abbreviation)

        exact: list[Candidate] = []
        prefix: list[Candidate] = []

        for sentence in self._sentences:
            # İki taraf da normalleştirilir: S4 etiketleri büyük harfle üretilir,
            # ``wanted`` ise küçültülmüş gelir.
            produced = normalize_abbreviation(scheme.abbreviate(sentence))
            if produced == wanted:
                exact.append(Candidate(text=sentence, score=1.0))
            elif produced.startswith(wanted):
                # Kullanıcı henüz yazmayı bitirmemiş olabilir: önek eşleşmesi
                # erken öneri olarak işe yarar.
                prefix.append(Candidate(text=sentence, score=0.5))

        return (exact + prefix)[: request.top_k]
