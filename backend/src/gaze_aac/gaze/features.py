"""Yüz landmark'larından bakış öznitelik vektörü çıkarma.

Ham piksel koordinatı kullanılmaz: kullanıcı başını 10 cm sağa kaydırdığında
tüm koordinatlar değişir ama bakış yönü aynı kalır. Bunun yerine iris
merkezinin göz köşelerine göre *göreli* konumu alınır ve yüz genişliğine
bölünerek ölçekten bağımsız hale getirilir.

Çıkan vektör 12 boyutludur ve ``docs/architecture.md`` içinde belgelenmiştir.
Sıralama değişirse kalibrasyon modelleri geçersizleşir; o yüzden
``FEATURE_NAMES`` listesi sözleşme gibi davranır.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# MediaPipe FaceLandmarker (refine_landmarks=True) çıktısındaki indeksler.
# Son 10 nokta (468-477) iki irisin çevresidir.
LEFT_IRIS = (468, 469, 470, 471, 472)
RIGHT_IRIS = (473, 474, 475, 476, 477)
LEFT_EYE_INNER = 133
LEFT_EYE_OUTER = 33
LEFT_EYE_TOP = 159
LEFT_EYE_BOTTOM = 145
RIGHT_EYE_INNER = 362
RIGHT_EYE_OUTER = 263
RIGHT_EYE_TOP = 386
RIGHT_EYE_BOTTOM = 374
FACE_LEFT = 234
FACE_RIGHT = 454
NOSE_TIP = 1
CHIN = 152
FOREHEAD = 10

FEATURE_NAMES: tuple[str, ...] = (
    "left_iris_rel_x",
    "left_iris_rel_y",
    "right_iris_rel_x",
    "right_iris_rel_y",
    "left_eye_openness",
    "right_eye_openness",
    "head_yaw",
    "head_pitch",
    "head_roll",
    "face_scale",
    "iris_disparity_x",
    "iris_disparity_y",
)
FEATURE_DIM = len(FEATURE_NAMES)


@dataclass(frozen=True)
class EyeFeatures:
    """Öznitelik vektörü ve üretildiği karenin güven puanı."""

    values: np.ndarray
    confidence: float

    def as_list(self) -> list[float]:
        return [float(v) for v in self.values]


def _centroid(points: np.ndarray, indices: tuple[int, ...]) -> np.ndarray:
    return points[list(indices)].mean(axis=0)


def _relative_iris(
    points: np.ndarray, iris: tuple[int, ...], inner: int, outer: int, top: int, bottom: int
) -> tuple[float, float]:
    """İris merkezinin göz kutusu içindeki 0–1 konumu.

    0 = dış köşe, 1 = iç köşe. Göz kapalıysa dikey eksen anlamsızlaşır, bu
    yüzden göz açıklığı ayrı bir öznitelik olarak taşınır.
    """
    center = _centroid(points, iris)
    eye_width = float(np.linalg.norm(points[inner] - points[outer]))
    eye_height = float(np.linalg.norm(points[top] - points[bottom]))
    if eye_width < 1e-6 or eye_height < 1e-6:
        return 0.5, 0.5
    rel_x = float((center[0] - points[outer][0]) / (points[inner][0] - points[outer][0] + 1e-9))
    rel_y = float((center[1] - points[top][1]) / (points[bottom][1] - points[top][1] + 1e-9))
    return float(np.clip(rel_x, -1.0, 2.0)), float(np.clip(rel_y, -1.0, 2.0))


def _eye_openness(points: np.ndarray, top: int, bottom: int, inner: int, outer: int) -> float:
    """Göz açıklığının göz genişliğine oranı. Kırpma tespitinde de kullanılır."""
    height = float(np.linalg.norm(points[top] - points[bottom]))
    width = float(np.linalg.norm(points[inner] - points[outer]))
    return height / width if width > 1e-6 else 0.0


def _head_pose(points: np.ndarray) -> tuple[float, float, float]:
    """Kaba baş pozu: yaw, pitch, roll.

    Tam 3B poz çözümü yerine landmark oranlarından türetilen yaklaşık değerler
    kullanılır. Regresyon bunları düzeltici terim olarak kullandığı için
    mutlak doğrulukları değil, tutarlılıkları önemlidir.
    """
    left, right = points[FACE_LEFT], points[FACE_RIGHT]
    nose, chin, forehead = points[NOSE_TIP], points[CHIN], points[FOREHEAD]

    face_width = float(np.linalg.norm(right - left)) + 1e-9
    face_height = float(np.linalg.norm(chin - forehead)) + 1e-9

    # Burun, yüz genişliğinin ortasından ne kadar sapmış: yaw
    mid_x = (left[0] + right[0]) / 2.0
    yaw = float((nose[0] - mid_x) / face_width)

    # Burun, alın-çene ekseninde nerede: pitch
    mid_y = (forehead[1] + chin[1]) / 2.0
    pitch = float((nose[1] - mid_y) / face_height)

    # Yüz ekseninin eğimi: roll
    roll = float(np.arctan2(right[1] - left[1], right[0] - left[0]))

    return yaw, pitch, roll


def extract_features(landmarks: np.ndarray) -> EyeFeatures:
    """478x3 landmark dizisinden öznitelik vektörü üretir.

    Args:
        landmarks: MediaPipe çıktısı, normalize koordinatlar, şekil (478, 3).

    Raises:
        ValueError: Dizi beklenen şekilde değilse.
    """
    points = np.asarray(landmarks, dtype=np.float64)
    if points.ndim != 2 or points.shape[0] < 478 or points.shape[1] < 2:
        raise ValueError(
            f"478x3 landmark bekleniyordu, {points.shape} geldi. "
            "MediaPipe'ta refine_landmarks=True açık mı?"
        )

    lx, ly = _relative_iris(
        points, LEFT_IRIS, LEFT_EYE_INNER, LEFT_EYE_OUTER, LEFT_EYE_TOP, LEFT_EYE_BOTTOM
    )
    rx, ry = _relative_iris(
        points, RIGHT_IRIS, RIGHT_EYE_INNER, RIGHT_EYE_OUTER, RIGHT_EYE_TOP, RIGHT_EYE_BOTTOM
    )
    left_open = _eye_openness(points, LEFT_EYE_TOP, LEFT_EYE_BOTTOM, LEFT_EYE_INNER, LEFT_EYE_OUTER)
    right_open = _eye_openness(
        points, RIGHT_EYE_TOP, RIGHT_EYE_BOTTOM, RIGHT_EYE_INNER, RIGHT_EYE_OUTER
    )
    yaw, pitch, roll = _head_pose(points)
    face_scale = float(np.linalg.norm(points[FACE_RIGHT] - points[FACE_LEFT]))

    values = np.array(
        [lx, ly, rx, ry, left_open, right_open, yaw, pitch, roll, face_scale, lx - rx, ly - ry],
        dtype=np.float64,
    )

    # Her iki göz de kapalıysa kareye güvenilmez.
    confidence = float(np.clip(min(left_open, right_open) / 0.2, 0.0, 1.0))
    return EyeFeatures(values=values, confidence=confidence)
