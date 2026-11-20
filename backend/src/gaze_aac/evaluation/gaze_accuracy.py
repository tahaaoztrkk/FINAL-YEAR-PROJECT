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
BLOCK_LABELS = {"validation": "doğrulama", "head_moved": "baş oynamış"}
# ?bakis ve App'teki ızgara: 4 sütun x 3 satır.
GRID_COLUMNS = 4
GRID_ROWS = 3


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
    by_target: dict[tuple[float, float], list[tuple[float, float]]] = {}
    for frame in kept:
        px, py = model.predict(frame.features)
        ex = (px - frame.target[0]) * width_px * cm_per_px
        ey = (py - frame.target[1]) * height_px * cm_per_px
        dx_cm.append(abs(ex))
        dy_cm.append(abs(ey))
        errors_deg.append(_deg(math.hypot(ex, ey), distance_cm))
        hits.append(_cell(px, py) == _cell(*frame.target))
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
    )


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
        "düştüğü karelerin oranı (dwell yok, ham kare).",
        "",
    ]
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

    if len(recordings) > 1:
        lines += ["## Özet (yeni model)", ""]
        lines += ["| Kayıt | Gözlük | Doğrulama ° | Baş oynamış ° | Hücre isabeti (doğr.) |"]
        lines += ["|---|---|---|---|---|"]
        for recording, _, results in recordings:
            by_block = {r.block: r for r in results if r.model == "yeni"}
            val, head = by_block.get("validation"), by_block.get("head_moved")
            lines.append(
                f"| {recording.name} | {recording.glasses} "
                f"| {f'{val.mean_deg:.2f}' if val else '—'} "
                f"| {f'{head.mean_deg:.2f}' if head else '—'} "
                f"| {f'%{100 * val.cell_hit:.0f}' if val else '—'} |"
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
