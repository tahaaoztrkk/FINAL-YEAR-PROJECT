"""`?olcum` kayıtlarından bakış hatası (görme açısı derecesi).

Kayıtta üç blok vardır: 9 noktalı kalibrasyon, ızgaraya denk gelmeyen 8
doğrulama noktası, aynı 8 noktaya baş oynatılmış halde bakış. Model yalnızca
kalibrasyon bloğuyla eğitilir; hata yalnızca diğer iki blokta ölçülür, yani
ezber değil gerçek hata çıkar.

İki model karşılaştırılır:

- ``yeni``: sunucudaki ``GazeMapper`` (1. derece, koşullu baş pozu, kırpış filtresi)
- ``eski``: 10 Kasım öncesi model (12 öznitelik, 2. derece, filtre yok)

Kullanım (backend klasöründen)::

    python -m gaze_aac.evaluation.gaze_accuracy olcum-*.json --screen-cm 34.5 --distance-cm 60

Ekran genişliği ve mesafe dereceye çevirmek için gerekir; kayıtta yoktur.
Mesafeyi ölçüm sırasında cetvelle ölçüp not edin.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from ..gaze.calibration import CalibrationError, GazeMapper, _build_model, blink_threshold
from ..gaze.features import extract_features
from ..schemas.gaze import CalibrationSample

FORMAT = "gaze-aac/gaze-measure@1"
EVAL_BLOCKS = ("validation", "head_moved")
# validation: kalibrasyondaki gibi baş sabit, ızgaraya denk gelmeyen noktalar.
BLOCK_LABELS = {"validation": "baş sabit", "head_moved": "baş oynamış"}
# ?bakis ve App'teki ızgara: 4 sütun x 3 satır.
GRID_COLUMNS = 4
GRID_ROWS = 3
# Tuş boyutu kararı için karşılaştırılan düzenler (sütun, satır).
GRIDS: tuple[tuple[int, int], ...] = ((4, 3), (3, 3), (3, 2), (2, 2))


@dataclass(frozen=True)
class Frame:
    block: str
    target: tuple[float, float]
    features: np.ndarray


@dataclass(frozen=True)
class Recording:
    name: str
    glasses: str
    video: str
    screen_px: tuple[int, int]
    frames: list[Frame]


@dataclass(frozen=True)
class BlockResult:
    model: str
    block: str
    frames: int
    skipped_blinks: int
    mean_deg: float
    median_deg: float
    point_mean_deg: float
    horizontal_cm: float
    vertical_cm: float
    cell_hit: float
    # Hedef hücre merkezinde olsaydı: aynı hata vektörleriyle her düzende isabet.
    grid_hit: dict[tuple[int, int], float]


class _Predictor(Protocol):
    def predict(self, features: np.ndarray) -> tuple[float, float]: ...


class _OldModel:
    """10 Kasım öncesi sunucu modeli: tüm 12 öznitelik, 2. derece, filtre yok."""

    def __init__(self, samples: list[CalibrationSample]) -> None:
        features = np.array([s.features for s in samples])
        self._x = _build_model(2, 1.0).fit(features, [s.target_x for s in samples])
        self._y = _build_model(2, 1.0).fit(features, [s.target_y for s in samples])

    def predict(self, features: np.ndarray) -> tuple[float, float]:
        row = features.reshape(1, -1)
        x = float(np.clip(self._x.predict(row)[0], 0.0, 1.0))
        y = float(np.clip(self._y.predict(row)[0], 0.0, 1.0))
        return x, y


def load_recording(path: Path) -> Recording:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != FORMAT:
        raise ValueError(f"{path.name}: {FORMAT} biçiminde değil ({data.get('format')!r}).")

    frames = []
    for raw in data["frames"]:
        landmarks = np.asarray(raw["landmarks"], dtype=np.float64)
        target = (float(raw["target"][0]), float(raw["target"][1]))
        frames.append(Frame(raw["block"], target, extract_features(landmarks).values))

    video = data.get("video") or {}
    screen = data.get("screen") or {}
    return Recording(
        name=path.stem,
        glasses=str(data.get("glasses", "?")),
        video=f"{video.get('width', '?')}x{video.get('height', '?')}",
        screen_px=(int(screen.get("width") or 0), int(screen.get("height") or 0)),
        frames=frames,
    )


def _cell(x: float, y: float) -> tuple[int, int]:
    return min(int(x * GRID_COLUMNS), GRID_COLUMNS - 1), min(int(y * GRID_ROWS), GRID_ROWS - 1)


def _deg(cm: float, distance_cm: float) -> float:
    return math.degrees(math.atan2(cm, distance_cm))


def evaluate_block(
    model_name: str,
    model: _Predictor,
    frames: Sequence[Frame],
    block: str,
    *,
    threshold: float,
    screen_px: tuple[int, int],
    screen_cm: float,
    distance_cm: float,
) -> BlockResult | None:
    """Bir bloktaki tüm karelerde hata. Kırpış kareleri (?bakis gibi) atlanır."""
    width_px, height_px = screen_px
    cm_per_px = screen_cm / width_px
    block_frames = [f for f in frames if f.block == block]
    kept = [f for f in block_frames if (f.features[4] + f.features[5]) / 2 >= threshold]
    if not kept:
        return None

    errors_deg, dx_cm, dy_cm, hits = [], [], [], []
    offsets: list[tuple[float, float]] = []
    by_target: dict[tuple[float, float], list[tuple[float, float]]] = {}
    for frame in kept:
        px, py = model.predict(frame.features)
        ex = (px - frame.target[0]) * width_px * cm_per_px
        ey = (py - frame.target[1]) * height_px * cm_per_px
        dx_cm.append(abs(ex))
        dy_cm.append(abs(ey))
        errors_deg.append(_deg(math.hypot(ex, ey), distance_cm))
        hits.append(_cell(px, py) == _cell(*frame.target))
        offsets.append((px - frame.target[0], py - frame.target[1]))
        by_target.setdefault(frame.target, []).append((px, py))

    # Nokta ortalaması: titreşim çıkınca kalan sistematik kayma (doğruluk).
    point_errors = []
    for target, predictions in by_target.items():
        mx, my = np.mean(predictions, axis=0)
        ex = (mx - target[0]) * width_px * cm_per_px
        ey = (my - target[1]) * height_px * cm_per_px
        point_errors.append(_deg(math.hypot(ex, ey), distance_cm))

    return BlockResult(
        model=model_name,
        block=block,
        frames=len(kept),
        skipped_blinks=len(block_frames) - len(kept),
        mean_deg=float(np.mean(errors_deg)),
        median_deg=float(np.median(errors_deg)),
        point_mean_deg=float(np.mean(point_errors)),
        horizontal_cm=float(np.mean(dx_cm)),
        vertical_cm=float(np.mean(dy_cm)),
        cell_hit=float(np.mean(hits)),
        grid_hit=grid_hit_rates(offsets),
    )


def grid_hit_rates(offsets: Sequence[tuple[float, float]]) -> dict[tuple[int, int], float]:
    """Hata vektörleri hücre merkezine uygulanırsa her düzende isabet oranı.

    Ölçüm noktaları hücre sınırlarına göre rastgele yerlerde olduğu için ham
    hücre isabeti düzenler arasında karşılaştırılamaz. Bunun yerine her karenin
    hatası (normalize dx, dy) hedef hücrenin ortasından itibaren uygulanır:
    yarım hücre genişliğinden ve yüksekliğinden küçükse isabet. Varsayım: hata
    ekranın her yerinde benzer (kenarlarda genelde biraz daha büyüktür).
    """
    if not offsets:
        return {grid: 0.0 for grid in GRIDS}
    dx = np.abs(np.array([o[0] for o in offsets]))
    dy = np.abs(np.array([o[1] for o in offsets]))
    return {
        (columns, rows): float(np.mean((dx < 0.5 / columns) & (dy < 0.5 / rows)))
        for columns, rows in GRIDS
    }


def analyse(
    recording: Recording, *, screen_cm: float, distance_cm: float
) -> tuple[GazeMapper, list[BlockResult]]:
    if recording.screen_px[0] <= 0 or recording.screen_px[1] <= 0:
        raise ValueError(f"{recording.name}: kayıtta ekran boyutu yok.")
    calibration = [
        CalibrationSample(features=list(f.features), target_x=f.target[0], target_y=f.target[1])
        for f in recording.frames
        if f.block == "calibration"
    ]
    if not calibration:
        raise CalibrationError(f"{recording.name}: kalibrasyon bloğu boş.")

    new = GazeMapper()
    new.fit(calibration)
    old = _OldModel(calibration)
    threshold = blink_threshold(calibration)

    results = []
    for model_name, model in (("yeni", new), ("eski", old)):
        for block in EVAL_BLOCKS:
            result = evaluate_block(
                model_name,
                model,
                recording.frames,
                block,
                threshold=threshold,
                screen_px=recording.screen_px,
                screen_cm=screen_cm,
                distance_cm=distance_cm,
            )
            if result is not None:
                results.append(result)
    return new, results


def _summary(
    recordings: list[tuple[Recording, GazeMapper, list[BlockResult]]], *, screen_cm: float
) -> list[str]:
    """Paylaşılacak özet: kişi başına derece hatası ve ızgara düzenine göre isabet."""
    lines = [
        "## Özet (yeni model)",
        "",
        "| Kayıt | Gözlük | Baş sabit ° | Baş oynamış ° | Dikey cm (sabit / oynamış) |",
        "|---|---|---|---|---|",
    ]
    rows: dict[str, list[BlockResult]] = {block: [] for block in EVAL_BLOCKS}
    for recording, _, results in recordings:
        by_block = {r.block: r for r in results if r.model == "yeni"}
        for block, result in by_block.items():
            rows[block].append(result)
        fixed, moved = by_block.get("validation"), by_block.get("head_moved")
        lines.append(
            f"| {recording.name} | {recording.glasses} "
            f"| {f'{fixed.mean_deg:.2f}' if fixed else '—'} "
            f"| {f'{moved.mean_deg:.2f}' if moved else '—'} "
            f"| {f'{fixed.vertical_cm:.2f}' if fixed else '—'} / "
            f"{f'{moved.vertical_cm:.2f}' if moved else '—'} |"
        )
    lines.append("")

    width_px, height_px = recordings[0][0].screen_px
    aspect = height_px / width_px if width_px else 9 / 16
    header = " | ".join(
        f"{c}x{r} ({screen_cm / c:.1f}x{screen_cm * aspect / r:.1f} cm)" for c, r in GRIDS
    )
    lines += [
        "### Tuş boyutu: ızgara düzenine göre isabet",
        "",
        "Her karenin hatası hedef hücrenin ortasından uygulandığında aynı hücrede kalma oranı "
        "(dwell ve yumuşatma yok; ?bakis'teki dwell denemesi bunun üstüne çıkar).",
        "",
        f"| Kayıt | Koşul | {header} |",
        "|---|---|" + "---|" * len(GRIDS),
    ]
    for recording, _, results in recordings:
        for r in results:
            if r.model != "yeni":
                continue
            cells = " | ".join(f"%{100 * r.grid_hit[g]:.0f}" for g in GRIDS)
            lines.append(f"| {recording.name} | {BLOCK_LABELS[r.block]} | {cells} |")
    for block, block_rows in rows.items():
        if len(block_rows) > 1:
            cells = " | ".join(
                f"%{100 * float(np.mean([r.grid_hit[g] for r in block_rows])):.0f}" for g in GRIDS
            )
            lines.append(f"| **ortalama** | {BLOCK_LABELS[block]} | {cells} |")
    lines.append("")
    return lines


def format_report(
    recordings: list[tuple[Recording, GazeMapper, list[BlockResult]]],
    *,
    screen_cm: float,
    distance_cm: float,
) -> str:
    lines = [
        "# Bakış hatası (?olcum)",
        "",
        f"Ekran genişliği {screen_cm:g} cm, mesafe {distance_cm:g} cm "
        f"(bu mesafede 1° ≈ {2 * distance_cm * math.tan(math.radians(0.5)):.2f} cm). "
        f"Hücre isabeti: {GRID_COLUMNS}x{GRID_ROWS} ızgarada tahminin hedefle aynı hücreye "
        "düştüğü karelerin oranı (dwell yok, ham kare). Baş sabit: kalibrasyondaki gibi, "
        "ızgaraya denk gelmeyen 8 noktada. Baş oynamış: aynı noktalar, baş hafifçe oynatılmış.",
        "",
    ]
    lines += _summary(recordings, screen_cm=screen_cm)
    for recording, mapper, results in recordings:
        lines += [
            f"## {recording.name}",
            "",
            f"Gözlük: {recording.glasses} · video {recording.video} · ekran "
            f"{recording.screen_px[0]}x{recording.screen_px[1]} px · yeni model: "
            f"{', '.join(mapper.feature_names)} ({mapper.discarded_blinks} kırpış elendi)",
            "",
            "| Model | Blok | Hata ° (kare ort.) | Medyan ° | Nokta ort. ° | Yatay cm | Dikey cm "
            "| Hücre isabeti | Kare (kırpış) |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for r in results:
            lines.append(
                f"| {r.model} | {BLOCK_LABELS[r.block]} | {r.mean_deg:.2f} | {r.median_deg:.2f} "
                f"| {r.point_mean_deg:.2f} | {r.horizontal_cm:.2f} | {r.vertical_cm:.2f} "
                f"| %{100 * r.cell_hit:.0f} | {r.frames} ({r.skipped_blinks}) |"
            )
        lines.append("")

    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("files", nargs="+", type=Path, help="?olcum'dan indirilen JSON dosyaları")
    parser.add_argument("--screen-cm", type=float, default=34.5, help="ekranın fiziksel genişliği")
    parser.add_argument("--distance-cm", type=float, default=60.0, help="göz–ekran mesafesi")
    parser.add_argument("--out", type=Path, help="raporu Markdown dosyasına da yaz")
    args = parser.parse_args(argv)

    analysed = []
    for path in args.files:
        recording = load_recording(path)
        mapper, results = analyse(recording, screen_cm=args.screen_cm, distance_cm=args.distance_cm)
        analysed.append((recording, mapper, results))

    report = format_report(analysed, screen_cm=args.screen_cm, distance_cm=args.distance_cm)
    print(report)
    if args.out:
        args.out.write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
