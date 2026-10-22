"""MediaPipe FaceLandmarker sarmalayıcısı.

MediaPipe ağır bir bağımlılıktır ve yalnızca kamera ucunda gerekir. Testler,
simülasyon ve arayüz geliştirme bu modüle dokunmadan çalışır; o yüzden import
işlevin içinde yapılır ve eksikse anlaşılır bir hata verilir.

Model dosyası (`face_landmarker.task`) repoya konmaz. İlk çalıştırmada
``scripts/download_model.py`` ile indirilir.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .features import EyeFeatures, extract_features

DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "face_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)


class LandmarkerUnavailableError(RuntimeError):
    """MediaPipe kurulu değil veya model dosyası yok."""


@dataclass
class FaceLandmarker:
    """Kameradan gelen kareden 478 landmark ve öznitelik vektörü çıkarır.

    Args:
        model_path: ``.task`` model dosyasının yolu.
        running_mode: ``video`` akış için, ``image`` tek kare için.
    """

    model_path: Path = DEFAULT_MODEL_PATH
    running_mode: str = "video"
    _detector: Any = None

    def __post_init__(self) -> None:
        self._detector = None

    def _ensure_loaded(self) -> Any:
        if self._detector is not None:
            return self._detector

        try:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision
        except ImportError as exc:  # pragma: no cover - ortama bağlı
            raise LandmarkerUnavailableError(
                'MediaPipe kurulu değil. Kurmak için: pip install -e ".[gaze]"'
            ) from exc

        if not self.model_path.exists():
            raise LandmarkerUnavailableError(
                f"Model dosyası bulunamadı: {self.model_path}\n"
                "İndirmek için: python scripts/download_model.py"
            )

        options = mp_vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(self.model_path)),
            running_mode=(
                mp_vision.RunningMode.VIDEO
                if self.running_mode == "video"
                else mp_vision.RunningMode.IMAGE
            ),
            num_faces=1,
            # İris noktaları (468-477) yalnızca bu bayrak açıkken üretilir.
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        self._detector = mp_vision.FaceLandmarker.create_from_options(options)
        return self._detector

    def process(self, frame_rgb: np.ndarray, timestamp_ms: int) -> EyeFeatures | None:
        """Tek kareden öznitelik vektörü çıkarır.

        Args:
            frame_rgb: RGB kare, şekil (H, W, 3), dtype uint8.
            timestamp_ms: Karenin milisaniye zaman damgası (video modunda artan).

        Returns:
            Öznitelikler, yüz bulunamazsa ``None``.
        """
        import mediapipe as mp  # yerel import: modül yalnızca burada gerekiyor

        detector = self._ensure_loaded()
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

        result = (
            detector.detect_for_video(image, timestamp_ms)
            if self.running_mode == "video"
            else detector.detect(image)
        )
        if not result.face_landmarks:
            return None

        points = np.array([[lm.x, lm.y, lm.z] for lm in result.face_landmarks[0]], dtype=np.float64)
        return extract_features(points)

    def close(self) -> None:
        if self._detector is not None:
            self._detector.close()
            self._detector = None
