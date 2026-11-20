"""Python ve TypeScript öznitelik hesabının ortak test verisini üretir.

Çıktı: frontend/src/features/gaze/__fixtures__/features.json

Her vaka, öznitelik hesabının kullandığı landmark'ları (seyrek) ve
``extract_features``'ın o landmark'lar için döndürdüğü 12 sayıyı içerir.
Diğer noktalar (0.5, 0.5, 0) kabul edilir. İki taraf da bu dosyaya karşı test
edilir:

- backend/tests/test_gaze.py: Python hâlâ dosyadaki sonucu veriyor mu?
- frontend/src/features/gaze/features.test.ts: TypeScript aynı sonucu veriyor mu?

features.py bilerek değiştirildiyse bu betik yeniden çalıştırılır ve
features.ts aynı şekilde güncellenir. Rastgelelik sabit tohumlu, yani çıktı
her çalıştırmada aynıdır.

    python scripts/export_feature_fixture.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from gaze_aac.gaze import features as F

OUTPUT = (
    Path(__file__).resolve().parents[2]
    / "frontend/src/features/gaze/__fixtures__/features.json"
)

FILL = (0.5, 0.5, 0.0)

# Ölçüye uygun bir yüz (normalize koordinat): test_gaze._fake_landmarks ile aynı düzen.
BASE: dict[int, tuple[float, float, float]] = {
    F.LEFT_EYE_OUTER: (0.30, 0.40, 0.0),
    F.LEFT_EYE_INNER: (0.42, 0.40, 0.0),
    F.LEFT_EYE_TOP: (0.36, 0.37, 0.0),
    F.LEFT_EYE_BOTTOM: (0.36, 0.43, 0.0),
    F.RIGHT_EYE_OUTER: (0.70, 0.40, 0.0),
    F.RIGHT_EYE_INNER: (0.58, 0.40, 0.0),
    F.RIGHT_EYE_TOP: (0.64, 0.37, 0.0),
    F.RIGHT_EYE_BOTTOM: (0.64, 0.43, 0.0),
    F.FACE_LEFT: (0.25, 0.50, 0.0),
    F.FACE_RIGHT: (0.75, 0.50, 0.0),
    F.NOSE_TIP: (0.50, 0.50, -0.05),
    F.CHIN: (0.50, 0.75, 0.0),
    F.FOREHEAD: (0.50, 0.25, 0.0),
}
LEFT_IRIS_CENTER = (0.36, 0.40, -0.01)
RIGHT_IRIS_CENTER = (0.64, 0.40, -0.01)
# İris çevresindeki 4 nokta merkezin etrafında küçük bir halka.
IRIS_RING = ((0.0, 0.0), (0.012, 0.0), (0.0, -0.012), (-0.012, 0.0), (0.0, 0.012))

USED = sorted(set(BASE) | set(F.LEFT_IRIS) | set(F.RIGHT_IRIS))


def _face(rng: np.random.Generator, *, closed: str | None = None) -> np.ndarray:
    """Rastgele baş pozu, ölçek, konum ve bakışla bir yüz kurar."""
    points = np.tile(np.array(FILL), (478, 1))
    for index, xyz in BASE.items():
        points[index] = xyz

    for center, iris in ((LEFT_IRIS_CENTER, F.LEFT_IRIS), (RIGHT_IRIS_CENTER, F.RIGHT_IRIS)):
        gaze = rng.normal(0.0, 0.008, size=2)
        for (dx, dy), index in zip(IRIS_RING, iris, strict=True):
            points[index] = [center[0] + gaze[0] + dx, center[1] + gaze[1] + dy, center[2]]

    # Gerçekçi bozulmalar: roll, ölçek, kayma, burun sapması (yaw/pitch), z gürültüsü.
    angle = rng.normal(0.0, 0.15)
    scale = rng.uniform(0.6, 1.4)
    shift = rng.normal(0.0, 0.05, size=2)
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    center = np.array([0.5, 0.5])
    idx = np.array(USED)
    points[idx, :2] = (points[idx, :2] - center) @ rotation.T * scale + center + shift
    points[idx, 2] += rng.normal(0.0, 0.003, size=len(idx))
    points[F.NOSE_TIP, :2] += rng.normal(0.0, 0.02, size=2) * scale
    # Landmark gürültüsü: tüm kullanılan noktalara küçük titreşim.
    points[idx, :2] += rng.normal(0.0, 0.001, size=(len(idx), 2))

    # Kapak en sonda kapatılır: gürültü yüksekliği sıfırdan çıkarmasın, sıfır
    # yükseklik dalı (açıklık 0, iris (0.5, 0.5)) gerçekten test edilsin.
    if closed in ("left", "both"):
        points[F.LEFT_EYE_TOP] = points[F.LEFT_EYE_BOTTOM]
    if closed in ("right", "both"):
        points[F.RIGHT_EYE_TOP] = points[F.RIGHT_EYE_BOTTOM]
    return points


def _edge_cases() -> list[tuple[str, np.ndarray]]:
    rng = np.random.default_rng(1)
    cases: list[tuple[str, np.ndarray]] = []

    face = _face(rng)
    face[list(F.LEFT_IRIS), 0] += 0.5  # iris göz kutusunun çok dışında → clip(…, -1, 2)
    cases.append(("iris kutunun dışında (clip üst sınır)", face))

    face = _face(rng)
    face[list(F.RIGHT_IRIS), 0] -= 0.5
    cases.append(("iris kutunun dışında (clip alt sınır)", face))

    face = _face(rng)
    face[F.LEFT_EYE_INNER] = face[F.LEFT_EYE_OUTER]  # genişlik 0 → (0.5, 0.5), açıklık 0
    cases.append(("sol göz genişliği sıfır", face))

    face = np.tile(np.array(FILL), (478, 1))
    cases.append(("tüm noktalar aynı yerde", face))
    return cases


def _round_trip(points: np.ndarray) -> np.ndarray:
    """JSON'a yazılan sayılarla hesaplamak için: repr → float birebir döner."""
    return np.array([[float(repr(float(v))) for v in row] for row in points])


def build() -> dict[str, object]:
    rng = np.random.default_rng(20261120)
    faces: list[tuple[str, np.ndarray]] = [(f"rastgele {i + 1}", _face(rng)) for i in range(40)]
    faces += [
        ("sol göz kapalı", _face(rng, closed="left")),
        ("sağ göz kapalı", _face(rng, closed="right")),
        ("iki göz kapalı", _face(rng, closed="both")),
    ]
    faces += _edge_cases()

    cases = []
    for name, face in faces:
        face = _round_trip(face)
        result = F.extract_features(face)
        cases.append(
            {
                "name": name,
                "points": {
                    str(i): [float(v) for v in face[i]]
                    for i in range(478)
                    if tuple(face[i]) != FILL
                },
                "values": result.as_list(),
                "confidence": result.confidence,
            }
        )

    return {
        "about": "scripts/export_feature_fixture.py üretir; elle düzenlemeyin.",
        "feature_names": list(F.FEATURE_NAMES),
        "fill": list(FILL),
        "cases": cases,
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{OUTPUT} yazıldı")


if __name__ == "__main__":
    main()
