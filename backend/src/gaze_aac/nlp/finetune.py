"""Turkish-Gemma'nın QLoRA ile ince ayarı.

    python -m gaze_aac.nlp.finetune --dry-run   # veri denetimi; GPU ve torch gerekmez
    python -m gaze_aac.nlp.finetune             # Colab T4'te eğitim

Ayarlar teknik plandan gelir: r=16, alpha=32, lr=2e-4, 3 epoch, batch=4,
grad_accum=4. Tek fark uzunluk sınırı: planda 256, burada 384 (aşağıda).
Unsloth kuruluysa model onunla yüklenir (aynı T4'te yaklaşık yarı süre),
kurulu değilse PEFT ve bitsandbytes ile.

Kayıp yalnızca tamamlama, yani cümle üstünden hesaplanır: istem her kayıtta
neredeyse aynıdır, onu ezberletmek modele bir şey öğretmez. İstem, çıkarımda
``hf_local`` sağlayıcısının modele verdiği haliyle kodlanır ve cümlenin
sonuna EOS eklenir; model cümleyi bitirince durmayı da öğrenir.

Model yalnızca eğitim kümesinden üretilen çiftleri görür. Doğrulama kümesi
her epoch sonunda kaybı ölçer ve en iyi epoch'u seçer. Test kümesi yalnızca
sızıntı denetiminde okunur.

Ağır paketler (torch, transformers, peft, unsloth) işlev içinde içe aktarılır:
kuru çalıştırma ve testler bunlar olmadan çalışır.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import statistics
import subprocess
import time
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from ..data.corpus import Corpus, build_training_pairs
from .schemes import tokenize

# PyTorch'un kayıpta yok saydığı etiket değeri.
IGNORE_INDEX = -100

# Gemma 2'nin dikkat ve MLP katmanlarının hepsi. LoRA yalnızca dikkate
# takıldığında QLoRA makalesindeki kaliteye ulaşmıyor.
TARGET_MODULES = ("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj")

# Teknik plandaki ölçü: 12.000 örnek, 3 epoch (2.250 adım) T4'te 2–3 saat.
# Kaba süre tahmini için adım başına saniye; Unsloth bunu yarıya indirir.
_PLAN_SECONDS_PER_STEP = (3.2, 4.8)


@dataclass(frozen=True)
class Hyperparameters:
    """Eğitim ayarları. Varsayılanlar teknik plandaki değerlerdir."""

    epochs: float = 3.0
    learning_rate: float = 2e-4
    batch_size: int = 4
    grad_accum: int = 4
    # Plandaki 256, ek etiketi listesini taşıyan S4 istemleri (en uzunu ~700
    # karakter) için sınırda kalabilir ve sığmayan kayıt atılır. Dolgu toplu
    # iş içindeki en uzun kayda göre yapıldığı için sınırı yükseltmek bellek
    # ya da süre maliyeti getirmiyor.
    max_length: int = 384
    lora_r: int = 16
    lora_alpha: int = 32
    # Unsloth'un hızlı çekirdekleri yalnızca 0 ile çalışır. Aşırı öğrenmeye
    # karşı doğrulama kaybına göre en iyi epoch seçilir.
    lora_dropout: float = 0.0
    warmup_share: float = 0.05
    seed: int = 42

    @property
    def effective_batch(self) -> int:
        return self.batch_size * self.grad_accum


@dataclass(frozen=True)
class FinetuneConfig:
    """Bir eğitim koşusunun girdi ve çıktıları."""

    model_id: str
    pairs_path: Path
    output_dir: Path
    eval_path: Path | None = None
    backend: str = "auto"
    limit: int | None = None
    resume: bool = False
    hyper: Hyperparameters = field(default_factory=Hyperparameters)


@dataclass(frozen=True)
class TrainingExample:
    """Tek eğitim kaydı: istem, beklenen tamamlama ve denetim bilgileri."""

    prompt: str
    completion: str
    scheme: str = ""
    sentence: str = ""
    revealed: int = 0


class Tokenizer(Protocol):
    """Kodlamanın ihtiyaç duyduğu kadarı; HuggingFace tokenizer'ı buna uyar."""

    eos_token_id: int | None

    def __call__(self, text: str, *, add_special_tokens: bool = True) -> Mapping[str, Any]: ...


def _example_from_record(record: Mapping[str, Any]) -> TrainingExample:
    return TrainingExample(
        prompt=str(record["prompt"]),
        completion=str(record["completion"]),
        scheme=str(record.get("scheme", "")),
        sentence=str(record.get("sentence", str(record["completion"]).strip())),
        revealed=int(record.get("revealed", 0) or 0),
    )


def load_examples(path: Path, limit: int | None = None) -> list[TrainingExample]:
    """``build_corpus`` çıktısı olan eğitim çiftlerini okur.

    Raises:
        ValueError: Satır geçerli JSON değilse ya da istem/tamamlama eksikse.
            Bozuk bir satırı sessizce atlamak eğitim verisini fark edilmeden
            küçültür.
    """
    examples: list[TrainingExample] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number} geçerli JSON değil") from exc
            if not (
                isinstance(record, dict)
                and isinstance(record.get("prompt"), str)
                and isinstance(record.get("completion"), str)
                and record["completion"].strip()
            ):
                raise ValueError(f"{path}:{line_number} 'prompt' ve 'completion' metin olmalı")
            examples.append(_example_from_record(record))
            if limit is not None and len(examples) >= limit:
                break
    return examples


def examples_from_corpus(path: Path, limit: int | None = None) -> list[TrainingExample]:
    """Doğrulama cümlelerinden, eğitimle aynı kuralla kayıt üretir."""
    records = build_training_pairs(Corpus.load(path))
    examples = [_example_from_record(record) for record in records]
    return examples[:limit] if limit is not None else examples


def _match_key(text: str) -> str:
    return " ".join(tokenize(text))


def find_leaks(examples: list[TrainingExample], held_out: list[Path]) -> dict[Path, int]:
    """Eğitim çiftlerinde geçen ve ayrılmış kümelerde de bulunan cümle sayısı.

    Noktalama ve büyük harf yok sayılır: "Su istiyorum." ile "su istiyorum"
    aynı cümledir.
    """
    trained = {_match_key(example.sentence) for example in examples}
    leaks: dict[Path, int] = {}
    for path in held_out:
        if not path.exists():
            continue
        held = {_match_key(entry.text) for entry in Corpus.load(path).entries}
        leaks[path] = len(trained & held)
    return leaks


def encode_example(
    example: TrainingExample, tokenizer: Tokenizer, max_length: int
) -> dict[str, list[int]] | None:
    """Kaydı modele girecek kimliklere çevirir; sığmıyorsa ``None``.

    İstem ``hf_local`` ile aynı çağrıyla (özel belirteçler dahil) kodlanır,
    böylece model eğitimde ve çıkarımda aynı belirteç dizisini görür. Uzun
    kayıt kesilmez, atılır: yarım cümleyle eğitmek modele cümleyi yarıda
    bırakmayı öğretir.
    """
    prompt_ids = list(tokenizer(example.prompt)["input_ids"])
    completion_ids = list(tokenizer(example.completion, add_special_tokens=False)["input_ids"])
    if tokenizer.eos_token_id is not None:
        completion_ids.append(tokenizer.eos_token_id)

    input_ids = prompt_ids + completion_ids
    if not completion_ids or len(input_ids) > max_length:
        return None
    return {
        "input_ids": input_ids,
        "attention_mask": [1] * len(input_ids),
        "labels": [IGNORE_INDEX] * len(prompt_ids) + completion_ids,
    }


def encode_examples(
    examples: list[TrainingExample], tokenizer: Tokenizer, max_length: int
) -> tuple[list[dict[str, list[int]]], int]:
    """Bütün kayıtları kodlar. Dönen ikinci değer sığmadığı için atılanların sayısı."""
    features: list[dict[str, list[int]]] = []
    dropped = 0
    for example in examples:
        encoded = encode_example(example, tokenizer, max_length)
        if encoded is None:
            dropped += 1
        else:
            features.append(encoded)
    return features, dropped


def plan_steps(example_count: int, hyper: Hyperparameters) -> tuple[int, int, int]:
    """(epoch başına adım, toplam adım, ısınma adımı)."""
    per_epoch = math.ceil(example_count / hyper.effective_batch) if example_count else 0
    total = math.ceil(per_epoch * hyper.epochs)
    warmup = max(1, round(total * hyper.warmup_share)) if total else 0
    return per_epoch, total, warmup


def describe(examples: list[TrainingExample]) -> list[str]:
    """Kuru çalıştırmada gösterilen özet satırları."""
    if not examples:
        return ["  kayıt yok"]
    schemes = Counter(example.scheme or "?" for example in examples)
    revealed = sum(1 for example in examples if example.revealed)
    lengths = [len(example.prompt) + len(example.completion) for example in examples]
    per_scheme = ", ".join(f"{scheme} {count}" for scheme, count in sorted(schemes.items()))
    return [
        f"  {len(examples)} kayıt ({per_scheme}), {revealed} tanesinde ilk kelimeler açık yazılmış",
        f"  Uzunluk (istem + cümle, karakter): en kısa {min(lengths)}, "
        f"ortanca {int(statistics.median(lengths))}, en uzun {max(lengths)}",
    ]


def resolve_backend(requested: str) -> str:
    """``auto``: Unsloth kuruluysa o, değilse PEFT."""
    if requested != "auto":
        return requested
    return "unsloth" if importlib.util.find_spec("unsloth") is not None else "peft"


def _load_with_unsloth(config: FinetuneConfig) -> tuple[Any, Any]:
    # Unsloth, transformers'tan önce içe aktarılmalı; yamalarını öyle uygular.
    from unsloth import FastLanguageModel

    hyper = config.hyper
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=config.model_id,
        max_seq_length=hyper.max_length,
        dtype=None,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=hyper.lora_r,
        lora_alpha=hyper.lora_alpha,
        lora_dropout=hyper.lora_dropout,
        target_modules=list(TARGET_MODULES),
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=hyper.seed,
    )
    return model, tokenizer


def _load_with_peft(config: FinetuneConfig, dtype: Any) -> tuple[Any, Any]:
    import transformers
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    hyper = config.hyper
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=dtype,
    )
    # transformers 5 ``torch_dtype`` adını ``dtype`` yaptı.
    dtype_key = "dtype" if int(transformers.__version__.split(".")[0]) >= 5 else "torch_dtype"
    tokenizer = AutoTokenizer.from_pretrained(config.model_id)
    model = AutoModelForCausalLM.from_pretrained(
        config.model_id,
        quantization_config=quantization,
        device_map="auto",
        # Gemma 2'nin logit kırpması sdpa'da yok; eğitimde eager öneriliyor.
        attn_implementation="eager",
        **{dtype_key: dtype},
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    lora = LoraConfig(
        r=hyper.lora_r,
        lora_alpha=hyper.lora_alpha,
        lora_dropout=hyper.lora_dropout,
        target_modules=list(TARGET_MODULES),
        bias="none",
        task_type="CAUSAL_LM",
    )
    return get_peft_model(model, lora), tokenizer


def _package_versions(names: tuple[str, ...]) -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError, version

    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            continue
    return versions


def _git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parent,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def train(
    config: FinetuneConfig,
    train_examples: list[TrainingExample],
    eval_examples: list[TrainingExample],
) -> dict[str, Any]:
    """Modeli yükler, eğitir, adaptörü ve ``training_info.json`` dosyasını yazar."""
    backend = resolve_backend(config.backend)
    if backend == "unsloth":
        import unsloth  # noqa: F401  (transformers'tan önce gelmeli)

    import torch
    from transformers import DataCollatorForSeq2Seq, Trainer, TrainingArguments, set_seed
    from transformers.trainer_utils import get_last_checkpoint

    if not torch.cuda.is_available():
        raise SystemExit(
            "CUDA GPU bulunamadı. Colab'da: Çalışma zamanı → Çalışma zamanı türünü "
            "değiştir → T4 GPU."
        )

    hyper = config.hyper
    set_seed(hyper.seed)
    bf16 = bool(torch.cuda.is_bf16_supported())
    dtype = torch.bfloat16 if bf16 else torch.float16

    print(f"Model yükleniyor ({backend}): {config.model_id}")
    if backend == "unsloth":
        model, tokenizer = _load_with_unsloth(config)
    else:
        model, tokenizer = _load_with_peft(config, dtype)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    # Eğitimde dolgu sağa: cümle sonundaki EOS'un hemen ardından gelir.
    tokenizer.padding_side = "right"

    train_features, train_dropped = encode_examples(train_examples, tokenizer, hyper.max_length)
    eval_features, eval_dropped = encode_examples(eval_examples, tokenizer, hyper.max_length)
    lengths = [len(feature["input_ids"]) for feature in train_features]
    if not lengths:
        raise SystemExit(f"Hiçbir kayıt {hyper.max_length} belirtece sığmadı. --max-len artırın.")
    print(
        f"Belirteç uzunluğu: en kısa {min(lengths)}, ortanca {int(statistics.median(lengths))}, "
        f"en uzun {max(lengths)} (sınır {hyper.max_length})"
    )
    if train_dropped or eval_dropped:
        print(
            f"UYARI: sınıra sığmayan {train_dropped} eğitim ve {eval_dropped} doğrulama "
            "kaydı atıldı. Çoksa --max-len artırın."
        )

    _, total_steps, warmup_steps = plan_steps(len(train_features), hyper)
    has_eval = bool(eval_features)
    args = TrainingArguments(
        output_dir=str(config.output_dir),
        per_device_train_batch_size=hyper.batch_size,
        per_device_eval_batch_size=hyper.batch_size,
        gradient_accumulation_steps=hyper.grad_accum,
        num_train_epochs=hyper.epochs,
        learning_rate=hyper.learning_rate,
        lr_scheduler_type="cosine",
        warmup_steps=warmup_steps,
        optim="paged_adamw_8bit",
        bf16=bf16,
        fp16=not bf16,
        logging_steps=10,
        # fp16 taşması kaybı NaN yapar; varsayılan süzgeç bunu günlükte gizler.
        logging_nan_inf_filter=False,
        eval_strategy="epoch" if has_eval else "no",
        save_strategy="epoch",
        save_total_limit=2,
        load_best_model_at_end=has_eval,
        metric_for_best_model="eval_loss" if has_eval else None,
        greater_is_better=False if has_eval else None,
        report_to="none",
        seed=hyper.seed,
        data_seed=hyper.seed,
        remove_unused_columns=False,
    )
    collator = DataCollatorForSeq2Seq(
        tokenizer=tokenizer, padding=True, label_pad_token_id=IGNORE_INDEX, pad_to_multiple_of=8
    )
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_features,
        eval_dataset=eval_features or None,
        data_collator=collator,
    )

    resume_from = None
    if config.resume:
        resume_from = get_last_checkpoint(str(config.output_dir))
        print(f"Devam: {resume_from}" if resume_from else "Checkpoint yok, baştan başlanıyor.")

    print(f"Eğitim başlıyor: {len(train_features)} kayıt, {total_steps} adım")
    started = time.perf_counter()
    result = trainer.train(resume_from_checkpoint=resume_from)
    minutes = (time.perf_counter() - started) / 60.0

    trainer.save_model(str(config.output_dir))
    tokenizer.save_pretrained(str(config.output_dir))

    info: dict[str, Any] = {
        "model_id": config.model_id,
        "backend": backend,
        "hyperparameters": asdict(hyper),
        "target_modules": list(TARGET_MODULES),
        "pairs_path": str(config.pairs_path),
        "pairs_sha256": _sha256(config.pairs_path),
        "eval_path": str(config.eval_path) if config.eval_path else None,
        "train_examples": len(train_features),
        "train_dropped": train_dropped,
        "eval_examples": len(eval_features),
        "eval_dropped": eval_dropped,
        "steps": trainer.state.global_step,
        "train_loss": result.training_loss,
        "best_eval_loss": trainer.state.best_metric,
        "best_checkpoint": trainer.state.best_model_checkpoint,
        "eval_history": [
            {"epoch": entry.get("epoch"), "eval_loss": entry["eval_loss"]}
            for entry in trainer.state.log_history
            if "eval_loss" in entry
        ],
        "minutes": round(minutes, 1),
        "precision": "bf16" if bf16 else "fp16",
        "gpu": torch.cuda.get_device_name(0),
        "versions": _package_versions(
            ("torch", "transformers", "peft", "bitsandbytes", "accelerate", "unsloth")
        ),
        "git_commit": _git_commit(),
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (config.output_dir / "training_info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nAdaptör yazıldı: {config.output_dir} ({minutes:.0f} dk)")
    if info["best_eval_loss"] is not None:
        print(f"En iyi doğrulama kaybı: {info['best_eval_loss']:.4f} ({info['best_checkpoint']})")
    if math.isnan(result.training_loss):
        print(
            "UYARI: eğitim kaybı NaN. T4'te fp16 taşması olabilir; Unsloth ile "
            "ya da bf16 destekli bir GPU'da (L4, A100) tekrar deneyin."
        )
    return info


def build_parser() -> argparse.ArgumentParser:
    from ..config import get_settings

    settings = get_settings()
    plan = Hyperparameters()
    parser = argparse.ArgumentParser(description="Turkish-Gemma'yı QLoRA ile ince ayarla")
    parser.add_argument("--pairs", type=Path, default=settings.pairs_path, help="Eğitim çiftleri")
    parser.add_argument(
        "--eval", type=Path, default=settings.val_path, help="Doğrulama cümleleri (JSONL derlem)"
    )
    parser.add_argument("--no-eval", action="store_true", help="Doğrulama kaybını ölçme")
    parser.add_argument("--model", default=settings.hf_model_id)
    parser.add_argument("--out", type=Path, default=settings.adapter_dir, help="Adaptör klasörü")
    parser.add_argument("--epochs", type=float, default=plan.epochs)
    parser.add_argument("--lr", type=float, default=plan.learning_rate)
    parser.add_argument("--batch", type=int, default=plan.batch_size)
    parser.add_argument("--grad-accum", type=int, default=plan.grad_accum)
    parser.add_argument("--max-len", type=int, default=plan.max_length)
    parser.add_argument("--r", type=int, default=plan.lora_r)
    parser.add_argument("--alpha", type=int, default=plan.lora_alpha)
    parser.add_argument("--lora-dropout", type=float, default=plan.lora_dropout)
    parser.add_argument("--seed", type=int, default=plan.seed)
    parser.add_argument("--backend", choices=("auto", "unsloth", "peft"), default="auto")
    parser.add_argument("--limit", type=int, default=None, help="Yalnızca ilk N kayıt (deneme)")
    parser.add_argument("--resume", action="store_true", help="Son checkpoint'ten devam et")
    parser.add_argument("--dry-run", action="store_true", help="Veriyi denetle, model yükleme")
    return parser


def main(argv: list[str] | None = None) -> None:
    """Komut satırından çalıştırma: ``python -m gaze_aac.nlp.finetune``."""
    from ..config import get_settings

    args = build_parser().parse_args(argv)
    settings = get_settings()
    config = FinetuneConfig(
        model_id=args.model,
        pairs_path=args.pairs,
        output_dir=args.out,
        eval_path=None if args.no_eval else args.eval,
        backend=args.backend,
        limit=args.limit,
        resume=args.resume,
        hyper=Hyperparameters(
            epochs=args.epochs,
            learning_rate=args.lr,
            batch_size=args.batch,
            grad_accum=args.grad_accum,
            max_length=args.max_len,
            lora_r=args.r,
            lora_alpha=args.alpha,
            lora_dropout=args.lora_dropout,
            seed=args.seed,
        ),
    )

    if not config.pairs_path.exists():
        raise SystemExit(
            f"Eğitim çiftleri yok: {config.pairs_path}\n"
            "Önce üretin: python -m gaze_aac.data.build_corpus"
        )
    source = settings.source_corpus_path
    if source.exists() and source.stat().st_mtime > config.pairs_path.stat().st_mtime:
        print("UYARI: derlem eğitim çiftlerinden yeni. build_corpus'u yeniden çalıştırın.\n")

    train_examples = load_examples(config.pairs_path, limit=config.limit)
    print(f"Eğitim çiftleri: {config.pairs_path}")
    print("\n".join(describe(train_examples)))

    eval_examples: list[TrainingExample] = []
    if config.eval_path is not None:
        if not config.eval_path.exists():
            raise SystemExit(f"Doğrulama kümesi yok: {config.eval_path} (--no-eval ile atlayın)")
        eval_examples = examples_from_corpus(config.eval_path, limit=config.limit)
        print(f"Doğrulama: {config.eval_path}, {len(eval_examples)} kayıt")

    held_out = [path for path in (config.eval_path, settings.test_path) if path is not None]
    leaks = find_leaks(train_examples, held_out)
    if any(leaks.values()):
        detail = ", ".join(f"{path.name}: {count}" for path, count in leaks.items() if count)
        raise SystemExit(
            f"Sızıntı: eğitim çiftlerindeki cümleler ayrılmış kümede de var ({detail}).\n"
            "build_corpus'u yeniden çalıştırıp çiftleri baştan üretin."
        )
    checked = ", ".join(path.name for path in leaks) or "dosya bulunamadı"
    print(f"Sızıntı denetimi temiz ({checked})")

    hyper = config.hyper
    per_epoch, total, warmup = plan_steps(len(train_examples), hyper)
    low, high = (round(total * seconds / 60) for seconds in _PLAN_SECONDS_PER_STEP)
    print(
        f"Ayarlar: r={hyper.lora_r} alpha={hyper.lora_alpha} dropout={hyper.lora_dropout} "
        f"lr={hyper.learning_rate} epoch={hyper.epochs:g} "
        f"batch={hyper.batch_size}x{hyper.grad_accum} max_len={hyper.max_length}"
    )
    print(
        f"Adım: epoch başına {per_epoch}, toplam {total} (ısınma {warmup}). "
        f"Kaba tahmin T4'te {low}–{high} dk, Unsloth ile yarısı."
    )

    if args.dry_run:
        if train_examples:
            sample = train_examples[0]
            print(f"\nÖrnek istem:\n{sample.prompt}\nBeklenen tamamlama:{sample.completion}")
        print("\nKuru çalıştırma bitti, model yüklenmedi.")
        return

    config.output_dir.mkdir(parents=True, exist_ok=True)
    train(config, train_examples, eval_examples)


if __name__ == "__main__":
    main()
