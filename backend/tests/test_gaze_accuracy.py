"""?olcum analiz betiği: sentetik kayıtla uçtan uca."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from gaze_aac.evaluation import gaze_accuracy as ga

GRID = [(x, y) for y in (0.1, 0.5, 0.9) for x in (0.1, 0.5, 0.9)]
VALIDATION = [(0.3, 0.3), (0.7, 0.3), (0.3, 0.7), (0.7, 0.7), (0.2, 0.5), (0.8, 0.5)]


def _face(target: tuple[float, float], rng: np.random.Generator, *, blink: bool = False) -> list:
    """İrisi hedefe göre doğrusal kayan bir yüz (test_gaze._fake_landmarks düzeni)."""
    points = np.full((478, 3), 0.5)
    layout = {
        33: (0.30, 0.40), 133: (0.42, 0.40), 159: (0.36, 0.37), 145: (0.36, 0.43),
        263: (0.70, 0.40), 362: (0.58, 0.40), 386: (0.64, 0.37), 374: (0.64, 0.43),
        234: (0.25, 0.50), 454: (0.75, 0.50), 1: (0.50, 0.50), 152: (0.50, 0.75),
        10: (0.50, 0.25),
    }  # fmt: skip
    for index, (x, y) in layout.items():
        points[index] = [x, y, 0.0]
    dx = (target[0] - 0.5) * 0.06 + rng.normal(0, 0.0005)
    dy = (target[1] - 0.5) * 0.03 + rng.normal(0, 0.0005)
    for index in range(468, 473):
        points[index] = [0.36 + dx, 0.40 + dy, 0.0]
    for index in range(473, 478):
        points[index] = [0.64 + dx, 0.40 + dy, 0.0]
    if blink:
        points[159] = points[145]
        points[386] = points[374]
    return [[round(v, 5) for v in row] for row in points]


@pytest.fixture
def recording_file(tmp_path: Path) -> Path:
    rng = np.random.default_rng(0)
    frames = []
    for block, targets in (
        ("calibration", GRID),
        ("validation", VALIDATION),
        ("head_moved", VALIDATION),
    ):
        for target in targets:
            for i in range(20):
                frames.append(
                    {
                        "block": block,
                        "target": list(target),
                        "t": i / 30,
                        "landmarks": _face(target, rng, blink=block == "validation" and i == 0),
                    }
                )
    path = tmp_path / "olcum-test.json"
    path.write_text(
        json.dumps(
            {
                "format": ga.FORMAT,
                "glasses": "gozluksuz",
                "video": {"width": 640, "height": 480},
                "screen": {"width": 1920, "height": 1080},
                "frames": frames,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_learns_synthetic_recording(recording_file: Path) -> None:
    recording = ga.load_recording(recording_file)
    _, results = ga.analyse(recording, screen_cm=34.5, distance_cm=60.0)
    new = {r.block: r for r in results if r.model == "yeni"}

    assert set(new) == {"validation", "head_moved"}
    assert new["validation"].mean_deg < 0.5
    # y = 0.3 ve 0.7, 4x3 ızgarada satır sınırına (1/3, 2/3) çok yakın; gürültü
    # birkaç kareyi komşu hücreye düşürebilir.
    assert new["validation"].cell_hit > 0.95
    # Her doğrulama noktasının ilk karesi kırpış: atlanmalı.
    assert new["validation"].skipped_blinks == len(VALIDATION)


def test_cli_writes_report(recording_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "rapor.md"
    ga.main([str(recording_file), "--distance-cm", "60", "--out", str(out)])
    report = out.read_text(encoding="utf-8")
    assert "olcum-test" in report
    assert "doğrulama" in report and "baş oynamış" in report


def test_rejects_other_formats(tmp_path: Path) -> None:
    path = tmp_path / "landmarks.json"
    path.write_text(json.dumps({"format": "gaze-aac/landmarks@1", "frames": []}))
    with pytest.raises(ValueError, match="gaze-measure"):
        ga.load_recording(path)
