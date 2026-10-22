"""OpenAI uyumlu API üstünden genişletme.

Bu sağlayıcı üst sınır taban çizgisidir: "kaynak sınırsız olsaydı doğruluk
ne olurdu" sorusunun cevabı. Ürünün parçası değildir, çünkü sistemin
çevrimdışı çalışması gerekir; raporda karşılaştırma sütunu olarak yer alır.

API anahtarı ``.env`` dosyasına yazılır ve repoya girmez.
"""

from __future__ import annotations

import json

from ...schemas.expansion import Candidate, ExpansionRequest
from ..prompts import SYSTEM_PROMPT, build_prompt


class OpenAICompatibleProvider:
    """Sohbet tamamlama uç noktasına istek atar."""

    name = "openai_compatible"

    def __init__(self, base_url: str, api_key: str, model: str, timeout_s: float = 20.0) -> None:
        if not base_url or not api_key or not model:
            raise ValueError(
                "LLM_BASE_URL, LLM_API_KEY ve LLM_MODEL ayarlanmalı. "
                ".env dosyasına yazın, koda gömmeyin."
            )
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_id = model
        self.timeout_s = timeout_s

    async def expand(self, request: ExpansionRequest) -> list[Candidate]:
        import httpx

        prompt = build_prompt(request.abbreviation, scheme=request.scheme, context=request.context)
        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"{prompt}\n\n"
                        f"Tam olarak {request.top_k} farklı aday üret ve yalnızca "
                        'JSON dizi olarak döndür: ["cümle 1", "cümle 2", ...]'
                    ),
                },
            ],
            "temperature": 0.7,
        }

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]

        return _parse_candidates(content, request.top_k)


def _parse_candidates(content: str, top_k: int) -> list[Candidate]:
    """Model çıktısından aday listesi çıkarır.

    Model bazen JSON'u kod bloğuna sarar ya da düz satırlar döner; iki durumu
    da kaldırabilmek gerekir, aksi halde tek bir biçim sapması ölçümü bozar.
    """
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text.removeprefix("json").strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [
                Candidate(text=str(item).strip(), score=float(top_k - index))
                for index, item in enumerate(parsed[:top_k])
                if str(item).strip()
            ]
    except json.JSONDecodeError:
        pass

    lines = [line.strip(" -*\t\"'") for line in text.splitlines()]
    return [
        Candidate(text=line, score=float(top_k - index))
        for index, line in enumerate([line for line in lines if line][:top_k])
    ]
