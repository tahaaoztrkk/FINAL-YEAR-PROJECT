"""llama.cpp sunucusu (``llama-server``) üstünden genişletme.

Demo bilgisayarında ince ayarlı model GGUF dosyası olarak llama.cpp ile
çalışır: HuggingFace + bitsandbytes'tan belirgin hızlıdır ve Windows'ta kurulum
gerektirmez. Model Colab'da birleştirilip GGUF'a çevrilir (defterdeki
"GGUF dışa aktarma" bölümü).

Model düz istemle eğitildi; sohbet şablonu kullanılmaz. Bu yüzden
``/chat/completions`` değil, istemi olduğu gibi tamamlayan ``/completion``
uç noktası çağrılır ve istem ``hf_local`` ile birebir aynıdır.

Aday başına bir istek gider ve istekler aynı anda yollanır. Sunucu
``--parallel`` ile birden fazla yuvayla başlatılırsa bunları tek toplu işte
üretir; beş adayın süresi tek adayın süresine yakın olur. İlk aday açgözlü
(sıcaklık 0) üretilir, gerisi örneklemeyle; tekrar eden adaylar atılır.
Ek isteklerde (``attempt`` > 0) açgözlü aday yeniden üretilmez, bütün adaylar
yeni tohumlarla örneklenir.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ...schemas.expansion import Candidate, ExpansionRequest
from ..prompts import build_prompt


class LlamaCppProvider:
    """``llama-server`` ile aday cümle üretir."""

    name = "llamacpp"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080",
        max_tokens: int = 24,
        temperature: float = 0.7,
        timeout_s: float = 30.0,
        transport: Any = None,
    ) -> None:
        if not base_url:
            raise ValueError("LLAMACPP_URL ayarlanmalı, örn. http://127.0.0.1:8080")
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout_s = timeout_s
        # Testler sahte bir httpx taşıyıcısı verir; gerçekte None.
        self._transport = transport
        self.model_id: str | None = None

    def payload(self, prompt: str, index: int, attempt: int = 0, top_k: int = 1) -> dict[str, Any]:
        """Tek aday için istek gövdesi.

        İlk istekte ``index`` 0 açgözlü üretimdir. Tohum her istek ve aday
        için farklıdır: aynı tohum aynı cümleyi verir, ek istek boşa gider.
        """
        greedy = attempt == 0 and index == 0
        return {
            "prompt": prompt,
            "n_predict": self.max_tokens,
            "temperature": 0.0 if greedy else self.temperature,
            "top_p": 0.9,
            "seed": attempt * top_k + index,
            # Aday tek satırdır.
            "stop": ["\n"],
            # Aynı istemin önbelleğe alınmış hali sonraki adaylarda kullanılır.
            "cache_prompt": True,
        }

    async def expand(self, request: ExpansionRequest) -> list[Candidate]:
        import httpx

        prompt = build_prompt(request.abbreviation, scheme=request.scheme, context=request.context)
        async with httpx.AsyncClient(timeout=self.timeout_s, transport=self._transport) as client:
            responses = await asyncio.gather(
                *(
                    client.post(
                        f"{self.base_url}/completion",
                        json=self.payload(prompt, index, request.attempt, request.top_k),
                    )
                    for index in range(request.top_k)
                )
            )
        texts: list[str] = []
        for response in responses:
            response.raise_for_status()
            body = response.json()
            if self.model_id is None:
                model = body.get("model") or body.get("generation_settings", {}).get("model")
                self.model_id = str(model) if model else None
            texts.append(str(body.get("content", "")))
        return candidates_from_texts(texts)

    def warm_up(self) -> None:
        """Sunucuya ulaşılabildiğini ölçümden önce denetler."""
        import httpx

        try:
            httpx.get(f"{self.base_url}/health", timeout=5.0).raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"llama.cpp sunucusuna ulaşılamadı: {self.base_url}. "
                "llama-server çalışıyor mu? (docs/setup.md, 'Demo bilgisayarı')"
            ) from exc


def candidates_from_texts(texts: list[str]) -> list[Candidate]:
    """Ham tamamlamaları sıralı, tekrarsız adaylara çevirir.

    Sıra puanı belirler: ilk (açgözlü) aday en yüksek puanı alır.
    """
    candidates: list[Candidate] = []
    seen: set[str] = set()
    for index, text in enumerate(texts):
        cleaned = text.strip().split("\n")[0].strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        candidates.append(Candidate(text=cleaned, score=-float(index)))
    return candidates
