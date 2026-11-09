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


def supports_bf16(torch: Any) -> bool:
    """GPU bf16'yı donanımda çalıştırıyor mu (Ampere ve sonrası: L4, A100).

    ``torch.cuda.is_bf16_supported()`` T4'te de True dönebilir: bf16 orada
    yazılımla taklit edilir ve çok yavaştır. Unsloth da T4'te modeli fp16
    yükler; eğitim ayarı modelle aynı türde olmalı. Bu yüzden doğrudan
    işlem kapasitesine bakılır.
    """
    if not torch.cuda.is_available():
        return False
    major, _minor = torch.cuda.get_device_capability()
    return bool(major >= 8)


DECODINGS = ("beam_sample", "beam", "sample", "greedy")


def generation_kwargs(
    decoding: str, top_k: int, max_new_tokens: int, num_beams: int = 0
) -> dict[str, Any]:
    """``model.generate`` ayarları.

    - ``beam_sample``: ışın + örnekleme (eski davranış). Çeşitli ama en yavaşı.
    - ``beam``: örneklemesiz ışın araması. Aynı ışın sayısında biraz daha hızlı
      ve her çalıştırmada aynı sonucu verir.
    - ``sample``: ışınsız, ``top_k`` bağımsız örnek. Işın aramasından hızlı,
      ama adaylar tekrar edebilir (tekrarlar atılır).
    - ``greedy``: tek aday, en hızlısı. Aday listesi tek satır kalır.

    ``num_beams`` 0 ise aday sayısı kadar (en az 4) ışın kullanılır.
    """
    if decoding not in DECODINGS:
        raise ValueError(f"Bilinmeyen üretim yöntemi: {decoding!r}. Seçenekler: {DECODINGS}")
    common: dict[str, Any] = {"max_new_tokens": max_new_tokens}
    if decoding == "greedy":
        return {**common, "do_sample": False, "num_beams": 1, "num_return_sequences": 1}
    if decoding == "sample":
        return {
            **common,
            "do_sample": True,
            "temperature": 0.7,
            "top_p": 0.9,
            "num_beams": 1,
            "num_return_sequences": top_k,
        }
    beams = max(num_beams or max(top_k, 4), top_k)
    kwargs = {**common, "num_beams": beams, "num_return_sequences": top_k}
    if decoding == "beam_sample":
        return {**kwargs, "do_sample": True, "temperature": 0.7, "top_p": 0.9}
    return {**kwargs, "do_sample": False}


def dtype_kwargs(transformers_version: str, dtype: Any) -> dict[str, Any]:
    """transformers 5 ``torch_dtype`` adını ``dtype`` yaptı."""
    key = "dtype" if int(transformers_version.split(".")[0]) >= 5 else "torch_dtype"
    return {key: dtype}


class HuggingFaceProvider:
    """Yerel nedensel dil modeliyle aday cümle üretir."""

    name = "hf_local"

    def __init__(
        self,
        model_id: str,
        load_in_4bit: bool = True,
        adapter_path: str | None = None,
        max_new_tokens: int = 24,
        decoding: str = "beam_sample",
        num_beams: int = 0,
    ) -> None:
        self.model_id = model_id
        self.load_in_4bit = load_in_4bit
        self.adapter_path = adapter_path
        # Sonuç tablosunda sıfır atış ile ince ayarlı model ayrı satır olmalı.
        self.name = "hf_local+lora" if adapter_path else "hf_local"
        self.max_new_tokens = max_new_tokens
        # Ayar hatası model yüklenmeden, hemen görünsün.
        generation_kwargs(decoding, 1, max_new_tokens, num_beams)
        self.decoding = decoding
        self.num_beams = num_beams
        self._model: Any = None
        self._tokenizer: Any = None

    def _load(self) -> tuple[Any, Any]:
        if self._model is not None and self._tokenizer is not None:
            return self._model, self._tokenizer

        try:
            import torch
            import transformers
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - ortama bağlı
            raise RuntimeError(
                'transformers/torch kurulu değil. Kurmak için: pip install -e ".[llm]"'
            ) from exc

        # Eğitimle aynı tür: T4'te fp16, bf16 destekli GPU'da bf16.
        dtype = torch.bfloat16 if supports_bf16(torch) else torch.float16
        quantization_config = None
        if self.load_in_4bit:
            try:
                from transformers import BitsAndBytesConfig

                quantization_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=dtype,
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
            **dtype_kwargs(transformers.__version__, dtype),
        )

        if self.adapter_path:
            from peft import PeftModel

            model = PeftModel.from_pretrained(model, self.adapter_path)

        model.eval()
        self._model, self._tokenizer = model, tokenizer
        return model, tokenizer

    def warm_up(self) -> None:
        """Modeli şimdi yükler.

        Yükleme dakikalar sürer; ilk isteğe kalırsa o isteğin gecikmesine
        eklenir ve ölçülen ortalama gecikmeyi bozar.
        """
        self._load()

    def _generate(self, prompt: str, top_k: int, attempt: int = 0) -> list[Candidate]:
        import torch

        model, tokenizer = self._load()
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

        decoding = self.decoding
        if attempt > 0:
            # Ek istek: ışın araması aynı istemde aynı adayları verir. Yeni
            # aday için örnekleme gerekir; tohum her denemede farklıdır.
            decoding = "sample"
            torch.manual_seed(attempt)
        settings = generation_kwargs(decoding, top_k, self.max_new_tokens, self.num_beams)
        with torch.no_grad():
            output = model.generate(
                **inputs,
                **settings,
                # Aday tek satırdır; satır sonu gelince o dalı bitir.
                stop_strings=["\n"],
                tokenizer=tokenizer,
                output_scores=True,
                return_dict_in_generate=True,
                pad_token_id=tokenizer.eos_token_id,
            )

        prompt_length = int(inputs["input_ids"].shape[1])
        sequences = output.sequences[:, prompt_length:]
        texts = tokenizer.batch_decode(sequences, skip_special_tokens=True)

        scores = getattr(output, "sequences_scores", None)
        candidates: list[Candidate] = []
        seen: set[str] = set()
        for index, text in enumerate(texts):
            cleaned = text.strip().split("\n")[0].strip()
            # Örneklemede aynı cümle birkaç kez çıkabilir.
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            score = float(scores[index]) if scores is not None else -float(index)
            candidates.append(Candidate(text=cleaned, score=score))
        return candidates

    async def expand(self, request: ExpansionRequest) -> list[Candidate]:
        prompt = build_prompt(request.abbreviation, scheme=request.scheme, context=request.context)
        # Üretim CPU/GPU'yu bloklar; olay döngüsünü serbest bırak.
        return await asyncio.to_thread(self._generate, prompt, request.top_k, request.attempt)
