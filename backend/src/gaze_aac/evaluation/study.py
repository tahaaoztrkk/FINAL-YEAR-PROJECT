"""Kullanıcı testinin analizi.

    python -m gaze_aac.evaluation.study
    python -m gaze_aac.evaluation.study --survey data/sessions/anket.csv

Oturum kayıtlarını (``data/sessions/<katılımcı>/*.jsonl``) okur, her cümle
için ölçüleri çıkarır, katılımcı x koşul ortalamalarını alır ve A ile B'yi
eşleştirilmiş testle karşılaştırır. Çıktılar ``data/sessions/analiz/``
altına yazılır; o klasör de repoya girmez.

İstatistik etik kurul belgesindeki plana göre: farkların normalliği
Shapiro-Wilk ile sınanır; uyarsa eşleştirilmiş t testi, uymazsa Wilcoxon
işaretli sıralar testi kullanılır; etki büyüklüğü Cohen d_z. İki testin p
değeri de tabloda durur, seçilen test ayrıca yazılır.

Cümle başına ölçüler:
    sure_s        İlk seçimden doğru seslendirmeye kadar. Hedefi okuma süresi girmez.
    wpm           ``metrics.words_per_minute``
    ksr           1 - seçim / ``metrics.letter_by_letter_selections``, yüzde
    secim         Bütün seçimler (dwell ya da tıklama)
    duzeltme      Sil + Geri seçimleri
    yanlis_cikti  Hedefle eşleşmeyen seslendirme
    aday_sirasi   B'de söylenen cümlenin aday listesindeki yeri, 1 tabanlı;
                  cümle aday seçilmeden yazıldıysa boş

Alıştırma cümleleri ve atlanan cümleler ortalamalara girmez; atlananlar ayrı
sayılır. Analiz varsayılan olarak yalnızca K ile başlayan kodları okur:
ekibin deneme oturumları başka harfle (ör. P01) kaydedilir ve sonuçlara
karışmaz.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..study.protocol import sentences_match
from .metrics import keystroke_savings_rate, letter_by_letter_selections, words_per_minute

ALPHA = 0.05
SUS_ITEMS = tuple(f"sus{index}" for index in range(1, 11))
EXTRA_ITEMS = tuple(f"k{index}" for index in range(1, 6))
SUS_BENCHMARK = 68.0
_SUS_ABOVE = f"esik_{int(SUS_BENCHMARK)}_ustu_yuzde"

# A ile B'nin karşılaştırıldığı ölçüler, rapordaki sırayla.
COMPARED_MEASURES = ("wpm", "ksr", "sure_s", "secim", "duzeltme", "yanlis_cikti")


# --------------------------------------------------------------------------
# Kayıtları okuma
# --------------------------------------------------------------------------


def read_events(path: Path) -> list[dict[str, Any]]:
    """JSONL kaydını okur. Bozuk satır atlanır: elektrik kesilince son satır
    yarım kalabilir, o yüzden bütün dosyayı çöpe atmak yanlış olur."""
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                events.append(record)
    return events


@dataclass
class TrialResult:
    """Tek bir hedef cümlenin ölçüleri."""

    participant: str
    block_index: int
    trial_index: int
    condition: str
    scheme: str
    target: str
    practice: bool
    outcome: str
    correct: bool
    duration_s: float | None
    selections: int
    deletes: int
    backs: int
    wrong_outputs: int
    expands: int
    candidate_rank: int | None
    source: str

    @property
    def counted(self) -> bool:
        """Ortalamalara girer mi."""
        return not self.practice and self.outcome == "done" and self.correct

    @property
    def corrections(self) -> int:
        return self.deletes + self.backs

    @property
    def wpm(self) -> float | None:
        if not self.counted or not self.duration_s:
            return None
        return words_per_minute(self.target, self.duration_s)

    @property
    def ksr(self) -> float | None:
        if not self.counted:
            return None
        return keystroke_savings_rate(self.selections, letter_by_letter_selections(self.target))

    def as_row(self) -> dict[str, object]:
        return {
            "katilimci": self.participant,
            "blok": self.block_index + 1,
            "cumle": self.trial_index + 1,
            "kosul": self.condition,
            "sema": self.scheme,
            "hedef": self.target,
            "alistirma": self.practice,
            "sonuc": self.outcome,
            "dogru": self.correct,
            "sure_s": _round(self.duration_s, 2),
            "wpm": _round(self.wpm, 2),
            "ksr": _round(self.ksr, 1),
            "secim": self.selections,
            "duzeltme": self.corrections,
            "yanlis_cikti": self.wrong_outputs,
            "genisletme": self.expands,
            "aday_sirasi": None if self.candidate_rank is None else self.candidate_rank + 1,
            "dosya": self.source,
        }


@dataclass
class SessionInfo:
    """Bir kayıt dosyasının başındaki ayarlar."""

    participant: str
    source: str
    order: str
    provider: str
    scheme: str
    materials: str
    calibration_deg: float | None = None


@dataclass
class _OpenTrial:
    start: dict[str, Any]
    selections: list[dict[str, Any]] = field(default_factory=list)
    speaks: list[dict[str, Any]] = field(default_factory=list)
    expands: int = 0


def _close_trial(
    trial: _OpenTrial, end: dict[str, Any], participant: str, source: str
) -> TrialResult:
    start = trial.start
    target = str(start.get("target", ""))
    outcome = str(end.get("outcome", ""))
    correct = bool(end.get("correct", False))

    # Süre ilk seçimle başlar: katılımcının hedefi okuması yazma hızına girmez.
    duration = None
    if trial.selections:
        duration = float(end["t"]) - float(trial.selections[0]["t"])

    # Doğru seslendirmenin aday sırası; sunucu bunu söylenen metni son aday
    # listesinde arayarak yazar.
    rank = None
    if outcome == "done":
        for speak in reversed(trial.speaks):
            if sentences_match(str(speak.get("text", "")), target):
                value = speak.get("candidate_rank")
                rank = int(value) if isinstance(value, int) else None
                break

    target_ids = [str(selection.get("target_id", "")) for selection in trial.selections]
    return TrialResult(
        participant=participant,
        block_index=int(start.get("block_index", 0)),
        trial_index=int(start.get("trial_index", 0)),
        condition=str(start.get("condition", "")),
        scheme=str(start.get("scheme", "")),
        target=target,
        practice=bool(start.get("practice", False)),
        outcome=outcome,
        correct=correct,
        duration_s=duration,
        selections=len(trial.selections),
        deletes=target_ids.count("action:delete"),
        backs=target_ids.count("action:back"),
        wrong_outputs=sum(
            1 for speak in trial.speaks if not sentences_match(str(speak.get("text", "")), target)
        ),
        expands=trial.expands,
        candidate_rank=rank,
        source=source,
    )


def extract_trials(
    events: Iterable[dict[str, Any]], participant: str, source: str = ""
) -> tuple[list[TrialResult], SessionInfo | None]:
    """Tek kayıt dosyasından tamamlanan cümleleri ve oturum ayarlarını çıkarır.

    Başlayıp bitmeyen cümle (bağlantı koptu) sayılmaz; istemci yeni
    bağlantıda aynı cümleyi baştan başlatır.
    """
    results: list[TrialResult] = []
    info: SessionInfo | None = None
    current: _OpenTrial | None = None

    for event in events:
        kind = event.get("event")
        if kind == "study_start":
            info = SessionInfo(
                participant=participant,
                source=source,
                order=str(event.get("order", "")),
                provider=str(event.get("provider", "")),
                scheme=str(event.get("scheme", "")),
                materials=str(event.get("materials", "")),
            )
            current = None
        elif kind == "calibration_result":
            if info is not None and event.get("ok") and event.get("mean_error_deg") is not None:
                info.calibration_deg = float(event["mean_error_deg"])
        elif kind == "trial_start":
            current = _OpenTrial(start=event)
        elif current is None:
            continue
        elif kind == "selection":
            current.selections.append(event)
        elif kind == "speak":
            current.speaks.append(event)
        elif kind == "expand":
            current.expands += 1
        elif kind == "trial_end":
            same = (event.get("block_index"), event.get("trial_index")) == (
                current.start.get("block_index"),
                current.start.get("trial_index"),
            )
            if same:
                results.append(_close_trial(current, event, participant, source))
            current = None
        elif kind in ("study_end", "disconnect"):
            current = None

    return results, info


def load_study(
    sessions_dir: Path, prefix: str = "K"
) -> tuple[list[TrialResult], list[SessionInfo]]:
    """Bütün katılımcıların kayıtlarını okur.

    Bir katılımcının birden çok dosyası olabilir (bağlantı koptu). Dosyalar
    adlarındaki saate göre sırayla okunur; aynı cümle iki kez bittiyse
    sonuncusu geçerlidir.
    """
    trials: list[TrialResult] = []
    infos: list[SessionInfo] = []
    if not sessions_dir.exists():
        return trials, infos

    for participant_dir in sorted(path for path in sessions_dir.iterdir() if path.is_dir()):
        participant = participant_dir.name
        if not participant.startswith(prefix):
            continue
        latest: dict[tuple[int, int], TrialResult] = {}
        for path in sorted(participant_dir.glob("*.jsonl")):
            found, info = extract_trials(read_events(path), participant, path.name)
            for trial in found:
                latest[(trial.block_index, trial.trial_index)] = trial
            if info is not None:
                infos.append(info)
        trials.extend(latest[key] for key in sorted(latest))
    return trials, infos


# --------------------------------------------------------------------------
# Özetler
# --------------------------------------------------------------------------


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


def _mean(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _sd(values: Sequence[float]) -> float | None:
    return statistics.stdev(values) if len(values) >= 2 else None


@dataclass
class ConditionSummary:
    """Bir katılımcının bir koşuldaki ortalamaları."""

    participant: str
    condition: str
    counted: int
    skipped: int
    measures: dict[str, float | None]
    top1: float | None
    top5: float | None
    calibration_deg: float | None

    def as_row(self) -> dict[str, object]:
        return {
            "katilimci": self.participant,
            "kosul": self.condition,
            "cumle_sayisi": self.counted,
            "atlanan": self.skipped,
            **{name: _round(value, 2) for name, value in self.measures.items()},
            "ilk1": _round(self.top1, 1),
            "ilk5": _round(self.top5, 1),
            "kalibrasyon_deg": _round(self.calibration_deg, 2),
        }


def _measure(trial: TrialResult, name: str) -> float | None:
    values: dict[str, float | None] = {
        "wpm": trial.wpm,
        "ksr": trial.ksr,
        "sure_s": trial.duration_s,
        "secim": float(trial.selections),
        "duzeltme": float(trial.corrections),
        "yanlis_cikti": float(trial.wrong_outputs),
    }
    return values[name]


def summarize(
    trials: Sequence[TrialResult], infos: Sequence[SessionInfo] = ()
) -> list[ConditionSummary]:
    """Katılımcı x koşul ortalamaları. Eşleştirilmiş test bunların üstünde koşar."""
    calibration: dict[str, float] = {}
    for info in infos:
        if info.calibration_deg is not None:
            calibration[info.participant] = info.calibration_deg

    summaries: list[ConditionSummary] = []
    keys = sorted({(trial.participant, trial.condition) for trial in trials})
    for participant, condition in keys:
        group = [t for t in trials if (t.participant, t.condition) == (participant, condition)]
        counted = [trial for trial in group if trial.counted]
        measures: dict[str, float | None] = {}
        for name in COMPARED_MEASURES:
            values = [v for v in (_measure(trial, name) for trial in counted) if v is not None]
            measures[name] = _mean(values)

        top1 = top5 = None
        if condition == "B" and counted:
            ranks = [trial.candidate_rank for trial in counted]
            top1 = sum(1 for rank in ranks if rank == 0) / len(ranks) * 100.0
            top5 = sum(1 for rank in ranks if rank is not None and rank < 5) / len(ranks) * 100.0

        summaries.append(
            ConditionSummary(
                participant=participant,
                condition=condition,
                counted=len(counted),
                skipped=sum(1 for t in group if not t.practice and t.outcome == "skipped"),
                measures=measures,
                top1=top1,
                top5=top5,
                calibration_deg=calibration.get(participant),
            )
        )
    return summaries


@dataclass
class PairedTest:
    """A ile B'nin bir ölçüdeki eşleştirilmiş karşılaştırması. Fark = B - A."""

    measure: str
    n: int
    mean_a: float | None
    sd_a: float | None
    mean_b: float | None
    sd_b: float | None
    mean_diff: float | None
    shapiro_p: float | None
    t_p: float | None
    wilcoxon_p: float | None
    test: str
    p: float | None
    cohen_dz: float | None

    def as_row(self) -> dict[str, object]:
        return {
            "olcu": self.measure,
            "n": self.n,
            "ort_A": _round(self.mean_a, 2),
            "ss_A": _round(self.sd_a, 2),
            "ort_B": _round(self.mean_b, 2),
            "ss_B": _round(self.sd_b, 2),
            "fark_B_eksi_A": _round(self.mean_diff, 2),
            "shapiro_p": _round(self.shapiro_p, 4),
            "test": self.test,
            "p": _round(self.p, 4),
            "p_t": _round(self.t_p, 4),
            "p_wilcoxon": _round(self.wilcoxon_p, 4),
            "cohen_dz": _round(self.cohen_dz, 2),
        }


def _finite(value: Any) -> float | None:
    number = float(value)
    return number if math.isfinite(number) else None


def paired_comparison(measure: str, a: Sequence[float], b: Sequence[float]) -> PairedTest:
    """Shapiro-Wilk farkların normalliğini sınar; uyarsa t, uymazsa Wilcoxon.

    Normallik sınanamıyorsa (üçten az katılımcı ya da hepsinde aynı fark)
    parametrik olmayan test seçilir.
    """
    from scipy import stats

    if len(a) != len(b):
        raise ValueError("Eşleştirilmiş testte iki koşulun uzunluğu aynı olmalı")
    diff = [after - before for before, after in zip(a, b, strict=True)]
    n = len(diff)
    mean_diff = _mean(diff)
    sd_diff = _sd(diff)
    varied = bool(sd_diff)
    cohen_dz = mean_diff / sd_diff if mean_diff is not None and sd_diff else None

    shapiro_p = _finite(stats.shapiro(diff).pvalue) if n >= 3 and varied else None
    t_p = _finite(stats.ttest_rel(b, a).pvalue) if n >= 2 and varied else None
    wilcoxon_p = None
    if any(value != 0 for value in diff):
        try:
            wilcoxon_p = _finite(stats.wilcoxon(diff).pvalue)
        except ValueError:
            wilcoxon_p = None

    if shapiro_p is not None and shapiro_p >= ALPHA:
        test, p = "t", t_p
    elif wilcoxon_p is not None:
        test, p = "wilcoxon", wilcoxon_p
    else:
        test, p = "-", None

    return PairedTest(
        measure=measure,
        n=n,
        mean_a=_mean(a),
        sd_a=_sd(a),
        mean_b=_mean(b),
        sd_b=_sd(b),
        mean_diff=mean_diff,
        shapiro_p=shapiro_p,
        t_p=t_p,
        wilcoxon_p=wilcoxon_p,
        test=test,
        p=p,
        cohen_dz=cohen_dz,
    )


def compare_conditions(summaries: Sequence[ConditionSummary]) -> list[PairedTest]:
    """İki koşulda da ölçüsü olan katılımcılar üstünden A ile B'yi karşılaştırır."""
    by_key = {(s.participant, s.condition): s for s in summaries}
    participants = sorted({s.participant for s in summaries})
    tests: list[PairedTest] = []
    for measure in COMPARED_MEASURES:
        a: list[float] = []
        b: list[float] = []
        for participant in participants:
            first = by_key.get((participant, "A"))
            second = by_key.get((participant, "B"))
            if first is None or second is None:
                continue
            value_a, value_b = first.measures[measure], second.measures[measure]
            if value_a is None or value_b is None:
                continue
            a.append(value_a)
            b.append(value_b)
        tests.append(paired_comparison(measure, a, b))
    return tests


# --------------------------------------------------------------------------
# Anket
# --------------------------------------------------------------------------


def sus_score(answers: Sequence[int]) -> float:
    """SUS puanı (0–100): tek maddeler (yanıt - 1), çift maddeler (5 - yanıt), x 2.5.

    Raises:
        ValueError: On yanıt yoksa ya da biri 1–5 dışındaysa.
    """
    if len(answers) != len(SUS_ITEMS) or any(not 1 <= answer <= 5 for answer in answers):
        raise ValueError(f"SUS için 1–5 arası on yanıt gerekiyor: {list(answers)}")
    odd = sum(answer - 1 for answer in answers[0::2])
    even = sum(5 - answer for answer in answers[1::2])
    return (odd + even) * 2.5


@dataclass
class SurveyResult:
    participant: str
    sus: float | None
    extra: dict[str, int]


def load_survey(path: Path) -> list[SurveyResult]:
    """``katilimci,sus1..sus10,k1..k5`` sütunlu CSV. Boş hücre yanıtsız sayılır."""
    results: list[SurveyResult] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            participant = (row.get("katilimci") or "").strip().upper()
            if not participant:
                continue
            raw = [(row.get(item) or "").strip() for item in SUS_ITEMS]
            sus = sus_score([int(value) for value in raw]) if all(raw) else None
            extra = {
                item: int(value) for item in EXTRA_ITEMS if (value := (row.get(item) or "").strip())
            }
            results.append(SurveyResult(participant=participant, sus=sus, extra=extra))
    return results


def summarize_survey(results: Sequence[SurveyResult]) -> list[dict[str, object]]:
    """SUS ve kısa anketin madde ortalamaları."""
    rows: list[dict[str, object]] = []
    scores = [result.sus for result in results if result.sus is not None]
    rows.append(
        {
            "madde": "SUS",
            "n": len(scores),
            "ort": _round(_mean(scores), 1),
            "ss": _round(_sd(scores), 1),
            _SUS_ABOVE: _round(
                sum(1 for score in scores if score > SUS_BENCHMARK) / len(scores) * 100.0
                if scores
                else None,
                1,
            ),
        }
    )
    for item in EXTRA_ITEMS:
        values = [float(result.extra[item]) for result in results if item in result.extra]
        rows.append(
            {
                "madde": item,
                "n": len(values),
                "ort": _round(_mean(values), 2),
                "ss": _round(_sd(values), 2),
            }
        )
    return rows


def load_demographics(path: Path) -> list[dict[str, object]]:
    """Demografi tablosundaki her sütunun değer sayımları (katılımcı kodu hariç)."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    counts: list[dict[str, object]] = []
    columns = [name for name in (rows[0].keys() if rows else []) if name != "katilimci"]
    for column in columns:
        for value, count in sorted(
            Counter((row.get(column) or "").strip() for row in rows).items()
        ):
            counts.append({"sutun": column, "deger": value or "(boş)", "sayi": count})
    return counts


# --------------------------------------------------------------------------
# Çıktı
# --------------------------------------------------------------------------


def write_rows(rows: Sequence[dict[str, object]], path: Path) -> None:
    """CSV yazar. ``utf-8-sig``: Excel Türkçe karakterleri ancak böyle doğru açar."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def check_sessions(
    infos: Sequence[SessionInfo], summaries: Sequence[ConditionSummary]
) -> list[str]:
    """Sonucu geçersiz kılabilecek tutarsızlıklar."""
    warnings: list[str] = []
    providers = {info.provider for info in infos}
    if len(providers) > 1:
        warnings.append(f"Katılımcılar farklı sağlayıcılarla koştu: {sorted(providers)}")
    if "mock" in providers:
        warnings.append("mock sağlayıcıyla kayıt var; mock yalnızca deneme içindir")
    if len({info.materials for info in infos}) > 1:
        warnings.append("Deney cümleleri katılımcılar arasında değişmiş (materials farklı)")
    if len({info.scheme for info in infos}) > 1:
        warnings.append(f"Farklı şemalar: {sorted({info.scheme for info in infos})}")

    conditions: dict[str, set[str]] = {}
    for summary in summaries:
        conditions.setdefault(summary.participant, set()).add(summary.condition)
    for participant, seen in sorted(conditions.items()):
        if seen != {"A", "B"}:
            warnings.append(
                f"{participant} yalnızca {sorted(seen)} koşulunda; karşılaştırmaya girmez"
            )

    orders = Counter({info.participant: info.order for info in infos if info.order}.values())
    if orders and orders.get("AB", 0) != orders.get("BA", 0):
        warnings.append(f"Sıra dengesiz: AB={orders.get('AB', 0)}, BA={orders.get('BA', 0)}")
    return warnings


def _format(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def main(argv: Sequence[str] | None = None) -> None:
    """Komut satırından çalıştırma: ``python -m gaze_aac.evaluation.study``."""
    from ..config import get_settings

    settings = get_settings()
    parser = argparse.ArgumentParser(description="Kullanıcı testini analiz et")
    parser.add_argument("--sessions", type=Path, default=settings.sessions_dir)
    parser.add_argument("--out", type=Path, default=None, help="Varsayılan: <sessions>/analiz")
    parser.add_argument(
        "--survey", type=Path, default=None, help="Varsayılan: <sessions>/anket.csv, varsa"
    )
    parser.add_argument(
        "--demographics",
        type=Path,
        default=None,
        help="Varsayılan: <sessions>/katilimcilar.csv, varsa",
    )
    parser.add_argument(
        "--prefix",
        default="K",
        help='Yalnızca bu harfle başlayan kodlar (varsayılan K; hepsi için "")',
    )
    args = parser.parse_args(argv)

    out = args.out or args.sessions / "analiz"
    trials, infos = load_study(args.sessions, prefix=args.prefix)
    if not trials:
        raise SystemExit(
            f"Kayıt bulunamadı: {args.sessions}/{args.prefix}*/*.jsonl\n"
            "Deney arayüzünden bir oturum tamamlayın ya da --sessions ile klasörü verin."
        )

    summaries = summarize(trials, infos)
    tests = compare_conditions(summaries)
    write_rows([trial.as_row() for trial in trials], out / "cumleler.csv")
    write_rows([summary.as_row() for summary in summaries], out / "katilimci_kosul.csv")
    write_rows([test.as_row() for test in tests], out / "karsilastirma.csv")

    participants = sorted({trial.participant for trial in trials})
    print(f"{len(participants)} katılımcı, {sum(t.counted for t in trials)} ölçülen cümle")
    for warning in check_sessions(infos, summaries):
        print(f"UYARI: {warning}")

    print(f"\n{'ölçü':<14}{'n':>3}{'A ort':>9}{'B ort':>9}{'test':>10}{'p':>9}{'d_z':>7}")
    for test in tests:
        print(
            f"{test.measure:<14}{test.n:>3}{_format(test.mean_a):>9}{_format(test.mean_b):>9}"
            f"{test.test:>10}{_format(test.p, 4):>9}{_format(test.cohen_dz):>7}"
        )

    b_rows = [summary for summary in summaries if summary.condition == "B"]
    top1 = [s.top1 for s in b_rows if s.top1 is not None]
    top5 = [s.top5 for s in b_rows if s.top5 is not None]
    calibration = list(
        {
            s.participant: s.calibration_deg for s in summaries if s.calibration_deg is not None
        }.values()
    )
    print(f"\nB koşulu ilk-1: {_format(_mean(top1), 1)}%  ilk-5: {_format(_mean(top5), 1)}%")
    if calibration:
        print(f"Kalibrasyon hatası: ort {_format(_mean(calibration))}° (n={len(calibration)})")

    survey_path = args.survey or args.sessions / "anket.csv"
    if survey_path.exists():
        survey_rows = summarize_survey(load_survey(survey_path))
        write_rows(survey_rows, out / "anket_ozet.csv")
        sus = survey_rows[0]
        print(f"SUS: ort {sus['ort']} (n={sus['n']}, {SUS_BENCHMARK:.0f} üstü %{sus[_SUS_ABOVE]})")
    elif args.survey is not None:
        raise SystemExit(f"Anket dosyası bulunamadı: {survey_path}")

    demographics_path = args.demographics or args.sessions / "katilimcilar.csv"
    if demographics_path.exists():
        write_rows(load_demographics(demographics_path), out / "demografi.csv")

    print(f"\nTablolar: {out}")


if __name__ == "__main__":
    main()
