"""Kullanıcı testinin betimsel analizi (ön kayıt, Bölüm 3.3).

Kullanıcı testi 4 kişilik ekiple yapıldığı için hipotez testi yapılmaz ve
p değeri raporlanmaz. Bu modül ön kayıttaki betimsel tabloları üretir:

- katılımcı başına bir satır: A ve B'nin ortalama WPM'i, B/A oranı,
  cümle başına düzeltme, atlanan cümle sayısı, SUS ve kalibrasyon hatası;
- aynı WPM'ler bir kez de atlanan her cümleye 180 sn (atlama sınırı)
  verilerek hesaplanır, çünkü atlanan cümleleri ortalamadan çıkarmak yavaş
  koşulu olduğundan hızlı gösterir;
- koşul başına ortalama, en küçük ve en büyük değer; kaç katılımcının
  B'de daha hızlı olduğu.

    python -m gaze_aac.evaluation.study_descriptive --survey data/sessions/anket.csv

Kayıtlar ``study.load_study`` ile okunur (yalnızca ``K`` kodları); oturum
başına bütün ayrıntı ve p değerleri için ``gaze_aac.evaluation.study``
kullanılır, ama onun p değerleri rapora konmaz.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from gaze_aac.evaluation.metrics import words_per_minute
from gaze_aac.evaluation.study import (
    SessionInfo,
    SurveyResult,
    TrialResult,
    load_study,
    load_survey,
    write_rows,
)

SKIP_PENALTY_S = 180.0
CONDITIONS = ("A", "B")


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


@dataclass
class ConditionResult:
    """Bir katılımcının bir koşuldaki ölçülen cümleleri (alıştırmalar hariç)."""

    wpm: float | None
    wpm_penalized: float | None
    corrections: float | None
    counted: int
    skipped: int


def condition_result(
    trials: Sequence[TrialResult], skip_penalty_s: float = SKIP_PENALTY_S
) -> ConditionResult:
    """Tek katılımcı, tek koşul. ``trials`` alıştırmaları içerebilir; atlanır."""
    measured = [trial for trial in trials if not trial.practice]
    counted = [trial for trial in measured if trial.counted]
    skipped = [trial for trial in measured if trial.outcome == "skipped"]

    wpm = [value for value in (trial.wpm for trial in counted) if value is not None]
    penalized = wpm + [words_per_minute(trial.target, skip_penalty_s) for trial in skipped]
    return ConditionResult(
        wpm=_mean(wpm),
        wpm_penalized=_mean(penalized),
        corrections=_mean([float(trial.corrections) for trial in counted]),
        counted=len(counted),
        skipped=len(skipped),
    )


def _ratio(b: float | None, a: float | None) -> float | None:
    if a is None or b is None or a == 0:
        return None
    return b / a


def participant_table(
    trials: Sequence[TrialResult],
    infos: Sequence[SessionInfo] = (),
    survey: Sequence[SurveyResult] = (),
    skip_penalty_s: float = SKIP_PENALTY_S,
) -> list[dict[str, object]]:
    """Katılımcı başına bir satır, katılımcı koduna göre sıralı."""
    order = {info.participant: info.order for info in infos}
    calibration = {
        info.participant: info.calibration_deg for info in infos if info.calibration_deg is not None
    }
    sus = {result.participant: result.sus for result in survey}

    rows: list[dict[str, object]] = []
    for participant in sorted({trial.participant for trial in trials}):
        own = [trial for trial in trials if trial.participant == participant]
        result = {
            condition: condition_result(
                [trial for trial in own if trial.condition == condition], skip_penalty_s
            )
            for condition in CONDITIONS
        }
        a, b = result["A"], result["B"]
        rows.append(
            {
                "katilimci": participant,
                "sira": order.get(participant, ""),
                "wpm_A": _round(a.wpm),
                "wpm_B": _round(b.wpm),
                "oran_B_A": _round(_ratio(b.wpm, a.wpm)),
                "wpm180_A": _round(a.wpm_penalized),
                "wpm180_B": _round(b.wpm_penalized),
                "oran180_B_A": _round(_ratio(b.wpm_penalized, a.wpm_penalized)),
                "duzeltme_A": _round(a.corrections),
                "duzeltme_B": _round(b.corrections),
                "cumle_A": a.counted,
                "cumle_B": b.counted,
                "atlanan_A": a.skipped,
                "atlanan_B": b.skipped,
                "sus": _round(sus.get(participant), 1),
                "kalibrasyon_deg": _round(calibration.get(participant)),
            }
        )
    return rows


SUMMARY_MEASURES = (
    ("wpm", "WPM (atlananlar hariç)"),
    ("wpm180", "WPM (atlananlara 180 sn)"),
    ("duzeltme", "Cümle başına düzeltme"),
    ("atlanan", "Atlanan cümle"),
)


def condition_summary(rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    """Koşul başına ortalama, en küçük, en büyük; SUS ve B'de hızlı olanların sayısı."""

    def column(name: str) -> list[float]:
        values = (row.get(name) for row in rows)
        return [float(value) for value in values if isinstance(value, (int, float))]

    summary: list[dict[str, object]] = []
    for key, label in SUMMARY_MEASURES:
        line: dict[str, object] = {"olcu": label}
        for condition in CONDITIONS:
            values = column(f"{key}_{condition}")
            line[f"ort_{condition}"] = _round(_mean(values))
            line[f"min_{condition}"] = _round(min(values)) if values else None
            line[f"max_{condition}"] = _round(max(values)) if values else None
        summary.append(line)

    sus = column("sus")
    summary.append(
        {
            "olcu": "SUS (yalnızca B)",
            "ort_B": _round(_mean(sus), 1),
            "min_B": _round(min(sus), 1) if sus else None,
            "max_B": _round(max(sus), 1) if sus else None,
        }
    )
    return summary


def faster_with_b(rows: Sequence[dict[str, object]], key: str = "wpm") -> tuple[int, int]:
    """(B'de daha hızlı olan katılımcı sayısı, iki koşulu da olan katılımcı sayısı)."""
    pairs: list[tuple[float, float]] = []
    for row in rows:
        a, b = row.get(f"{key}_A"), row.get(f"{key}_B")
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            pairs.append((float(a), float(b)))
    return sum(1 for a, b in pairs if b > a), len(pairs)


def _markdown(rows: Sequence[dict[str, object]]) -> str:
    if not rows:
        return "(veri yok)"
    headers = list(rows[0].keys())
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        lines.append(
            "| " + " | ".join("" if row.get(h) is None else str(row.get(h)) for h in headers) + " |"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    from ..config import get_settings

    settings = get_settings()
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--sessions", type=Path, default=settings.sessions_dir)
    parser.add_argument("--survey", type=Path, default=None, help="anket.csv (SUS için)")
    parser.add_argument("--out", type=Path, default=None, help="Varsayılan: <sessions>/analiz")
    parser.add_argument("--skip-penalty", type=float, default=SKIP_PENALTY_S)
    args = parser.parse_args(argv)

    trials, infos = load_study(args.sessions)
    if not trials:
        print(f"{args.sessions} altında K kodlu kayıt yok.")
        return
    survey = load_survey(args.survey) if args.survey else []

    rows = participant_table(trials, infos, survey, args.skip_penalty)
    summary = condition_summary(rows)
    out = args.out or args.sessions / "analiz"
    out.mkdir(parents=True, exist_ok=True)
    write_rows(rows, out / "katilimci_tablosu.csv")
    write_rows(summary, out / "kosul_ozeti.csv")

    faster, n = faster_with_b(rows)
    faster180, n180 = faster_with_b(rows, "wpm180")
    print("Katılımcı başına\n\n" + _markdown(rows) + "\n")
    print("Koşul başına\n\n" + _markdown(summary) + "\n")
    print(f"B'de daha hızlı: {faster}/{n} (atlananlara 180 sn ile: {faster180}/{n180})")
    print(f"Dosyalar: {out}")


if __name__ == "__main__":
    main()
