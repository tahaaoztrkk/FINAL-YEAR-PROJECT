"""Yerel HuggingFace modeliyle genişletme.

Varsayılan model Turkish-Gemma-9b; 4-bit yüklendiğinde 16 GB belleğe sığar,
yani ücretsiz Colab T4 yeterlidir. İnce ayar LoRA adaptörü olarak üretilir,
``HF_ADAPTER_PATH`` ile buraya takılır.

Model yükleme pahalıdır (dakikalar sürer), bu yüzden tembel yapılır ve
sağlayıcı yaşam boyu tek örnek tutulur. Üretim çağrısı bloklayıcı olduğundan
olay döngüsünü kilitlememek için iş parçacığına taşınır.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ...schemas.expansion import Candidate, ExpansionRequest
from ..prompts import build_prompt


class HuggingFaceProvider:
    """Yerel nedensel dil modeliyle aday cümle üretir."""

    name = "hf_local"

    def __init__(
        self,
        model_id: str,
        load_in_4bit: bool = True,
        adapter_path: str | None = None,
        max_new_tokens: int = 48,
    ) -> None:
        self.model_id = model_id
        self.load_in_4bit = load_in_4bit
        self.adapter_path = adapter_path
        # Sonuç tablosunda sıfır atış ile ince ayarlı model ayrı satır olmalı.
        self.name = "hf_local+lora" if adapter_path else "hf_local"
        self.max_new_tokens = max_new_tokens
        self._model: Any = None
        self._tokenizer: Any = None

    def _load(self) -> tuple[Any, Any]:
        if self._model is not None and self._tokenizer is not None:
            return self._model, self._tokenizer

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - ortama bağlı
            raise RuntimeError(
                'transformers/torch kurulu değil. Kurmak için: pip install -e ".[llm]"'
            ) from exc

        quantization_config = None
        if self.load_in_4bit:
            try:
                from transformers import BitsAndBytesConfig

                quantization_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                )
            except ImportError:  # pragma: no cover - ortama bağlı
                quantization_config = None

        tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            quantization_config=quantization_config,
            device_map="auto",
            torch_dtype=torch.float16,
        )

        if self.adapter_path:
            from peft import PeftModel

            model = PeftModel.from_pretrained(model, self.adapter_path)

        model.eval()
        self._model, self._tokenizer = model, tokenizer
        return model, tokenizer

    def _generate(self, prompt: str, top_k: int) -> list[Candidate]:
        import torch

        model, tokenizer = self._load()
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

        with torch.no_grad():
            output = model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                num_return_sequences=top_k,
                # Işın örnekleme: çeşitlilik olmadan beş aday birbirinin aynısı olur.
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
                num_beams=max(top_k, 4),
                output_scores=True,
                return_dict_in_generate=True,
                pad_token_id=tokenizer.eos_token_id,
            )

        prompt_length = int(inputs["input_ids"].shape[1])
        sequences = output.sequences[:, prompt_length:]
        texts = tokenizer.batch_decode(sequences, skip_special_tokens=True)

        scores = getattr(output, "sequences_scores", None)
        candidates: list[Candidate] = []
        for index, text in enumerate(texts):
            cleaned = text.strip().split("\n")[0].strip()
            if not cleaned:
                continue
            score = float(scores[index]) if scores is not None else -float(index)
            candidates.append(Candidate(text=cleaned, score=score))
        return candidates

    async def expand(self, request: ExpansionRequest) -> list[Candidate]:
        prompt = build_prompt(request.abbreviation, scheme=request.scheme, context=request.context)
        # Üretim CPU/GPU'yu bloklar; olay döngüsünü serbest bırak.
        return await asyncio.to_thread(self._generate, prompt, request.top_k)
