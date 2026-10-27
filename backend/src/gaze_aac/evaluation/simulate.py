"""Çevrimdışı simülasyon.

Projenin asıl bulgusu buradan çıkar ve göz takibi hiç çalışmasa bile elde
kalır: her test cümlesi için kısaltma üretilir, sağlayıcıdan adaylar istenir,
kullanıcının davranışı modellenir.

Modellenen kullanıcı şöyle davranır: doğru cümle listede varsa seçer; yoksa
bir karakter daha girer ve tekrar dener. Bu, gerçek kullanıcının yapacağı
şeyin iyimser ama tutarlı bir yaklaşımıdır ve bütün koşullarda aynı
uygulandığı için karşılaştırmayı adil kılar.
"""

from __future__ import annotations

import asyncio
import csv
import time
from dataclasses import dataclass
from pathlib import Path

from ..nlp.expander import ExpansionService
from ..nlp.schemes import get_scheme, normalize_abbreviation
from ..schemas.expansion import ExpansionRequest
from .metrics import SimulationStats, character_count


@dataclass
class SimulationCase:
    """Tek bir test cümlesi ve varsa bağlamı."""

    text: str
    context: str | None = None


def _normalize_for_match(text: str) -> str:
    """Karşılaştırma için cümleyi sadeleştirir: noktalama ve büyük harf yok sayılır."""
    from ..nlp.schemes import tokenize

    return " ".join(tokenize(text))


async def simulate_case(
    case: SimulationCase,
    service: ExpansionService,
    scheme_id: str,
    top_k: int,
    use_context: bool,
    max_rounds: int = 5,
) -> tuple[int, int | None, float]:
    """Tek cümle için kullanıcı davranışını modeller.

    Returns:
        (yapılan seçim sayısı, doğru adayın sırası veya None, toplam gecikme ms)
    """
    scheme = get_scheme(scheme_id)
    full_abbreviation = scheme.abbreviate(case.text)
    pieces = full_abbreviation.split()
    target = _normalize_for_match(case.text)

    base_selections = scheme.keystrokes(case.text)
    total_latency = 0.0

    # Tur 1: tam kısaltma. Sonraki turlarda kullanıcı cümlenin başından
    # itibaren birer kelime açık yazar (çıkmaz sokak olmaması ilkesi).
    for round_index in range(max_rounds):
        if round_index == 0:
            abbreviation = full_abbreviation
            extra_selections = 0
        else:
            words = target.split()
            if round_index > len(words):
                break
            revealed = words[:round_index]
            rest = pieces[round_index:]
            abbreviation = " ".join([*revealed, *rest])
            extra_selections = sum(len(w) for w in revealed) - round_index

        request = ExpansionRequest(
            abbreviation=normalize_abbreviation(abbreviation),
            scheme=scheme_id,
            context=case.context if use_context else None,
            top_k=top_k,
        )
        result = await service.expand(request)
        total_latency += result.latency_ms

        for rank, candidate in enumerate(result.candidates):
            if _normalize_for_match(candidate.text) == target:
                # Seçim maliyeti: kısaltma + aday listesinden seçim (1 dwell)
                return base_selections + extra_selections + 1, rank, total_latency

    # Hiç bulunamadı: kullanıcı cümleyi harf harf yazmak zorunda kaldı.
    return character_count(case.text), None, total_latency


async def run_condition(
    cases: list[SimulationCase],
    service: ExpansionService,
    scheme_id: str,
    top_k: int = 5,
    use_context: bool = False,
) -> SimulationStats:
    """Tek bir koşulu (şema x sağlayıcı x bağlam) baştan sona koşar."""
    stats = SimulationStats(
        scheme=scheme_id, provider=service.provider_name, with_context=use_context
    )

    for case in cases:
        selections, rank, latency = await simulate_case(
            case, service, scheme_id, top_k, use_context
        )
        stats.sentence_count += 1
        stats.total_selections += selections
        stats.total_characters += character_count(case.text)
        stats.ranks.append(rank)
        stats.latencies_ms.append(latency)

    return stats


async def run_grid(
    cases: list[SimulationCase],
    services: dict[str, ExpansionService],
    scheme_ids: list[str],
    context_options: tuple[bool, ...] = (False, True),
    top_k: int = 5,
) -> list[SimulationStats]:
    """Tüm koşulları koşar: şema x sağlayıcı x bağlam.

    Dört şema, üç sağlayıcı ve iki bağlam seçeneği 24 koşul eder. Tek çağrı
    tek CSV üretir; rapora giden tablo budur.
    """
    results: list[SimulationStats] = []
    for provider_name, service in services.items():
        for scheme_id in scheme_ids:
            for use_context in context_options:
                started = time.perf_counter()
                stats = await run_condition(cases, service, scheme_id, top_k, use_context)
                results.append(stats)
                elapsed = time.perf_counter() - started
                print(
                    f"[{provider_name:>18}] {scheme_id} "
                    f"bağlam={'var' if use_context else 'yok':>3} "
                    f"KSR={stats.ksr:5.1f}%  ilk1={stats.top1:5.1f}%  "
                    f"ilk5={stats.top5:5.1f}%  ({elapsed:.1f} sn)"
                )
    return results


def write_csv(results: list[SimulationStats], path: Path) -> None:
    """Sonuçları CSV'ye yazar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [stats.as_row() for stats in results]
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def load_cases(path: Path, limit: int | None = None) -> list[SimulationCase]:
    """JSONL derleminden test vakalarını okur."""
    import json

    cases: list[SimulationCase] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            text = record.get("text")
            if not isinstance(text, str) or not text:
                continue
            cases.append(SimulationCase(text=text, context=record.get("context")))
            if limit is not None and len(cases) >= limit:
                break
    return cases


def main() -> None:
    """Komut satırından çalıştırma: ``python -m gaze_aac.evaluation.simulate``."""
    import argparse

    from ..config import get_settings
    from ..nlp.expander import build_provider

    parser = argparse.ArgumentParser(description="Kısaltma şemalarını karşılaştır")
    parser.add_argument(
        "--corpus", type=Path, default=None, help="Değerlendirme cümleleri (varsayılan: val)"
    )
    parser.add_argument(
        "--train", type=Path, default=None, help="Sağlayıcıların öğreneceği cümleler"
    )
    parser.add_argument("--out", type=Path, default=Path("results/simulation.csv"))
    parser.add_argument("--providers", nargs="+", default=["mock"])
    parser.add_argument("--schemes", nargs="+", default=["S1", "S2", "S3", "S4"])
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    settings = get_settings()
    # Test kümesi Ocak'a kadar kapalı: geliştirme sırasında doğrulama kümesi
    # ölçülür, sağlayıcılar yalnızca eğitim kümesini görür.
    corpus = args.corpus or settings.val_path
    train = args.train or settings.train_path
    for path in (corpus, train):
        if not path.exists():
            raise SystemExit(
                f"Derlem bulunamadı: {path}\nÖnce üretin: python -m gaze_aac.data.build_corpus"
            )

    cases = load_cases(corpus, limit=args.limit)
    services = {
        name: ExpansionService(build_provider(name, settings, corpus_path=train))
        for name in args.providers
    }

    results = asyncio.run(run_grid(cases, services, args.schemes, top_k=args.top_k))
    write_csv(results, args.out)
    print(f"\n{len(results)} koşul yazıldı: {args.out}")


if __name__ == "__main__":
    main()
