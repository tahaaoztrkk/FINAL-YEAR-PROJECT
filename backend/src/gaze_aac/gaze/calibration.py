"""Öznitelik vektöründen ekran koordinatına eşleme.

Kalibrasyon verisi küçüktür (9 nokta x ~30 kare), bu yüzden derin ağ değil
düzenlileştirilmiş regresyon kullanılır. İkinci derece polinom açılımı,
kameranın ve gözün doğrusal olmayan davranışını yakalayacak kadar esnek,
ezberlemeyecek kadar kısıtlıdır.

Doğruluk piksel cinsinden ölçülür, sonra görme açısı derecesine çevrilir;
literatürde karşılaştırılabilir olan birim derecedir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

from ..schemas.gaze import CalibrationReport, CalibrationSample


class CalibrationError(RuntimeError):
    """Model eğitilemediğinde veya eğitilmeden kullanıldığında."""


def _build_model(degree: int, alpha: float) -> Pipeline:
    return Pipeline(
        [
            ("scale", StandardScaler()),
            ("poly", PolynomialFeatures(degree=degree, include_bias=False)),
            ("ridge", Ridge(alpha=alpha)),
        ]
    )


@dataclass
class GazeMapper:
    """Öznitelik vektörünü normalize ekran koordinatına çeviren model.

    x ve y için ayrı regresyon kullanılır; bu, eksenlerin birbirinden bağımsız
    hata profillerine sahip olmasına izin verir (dikey hata yatayın tipik
    olarak iki katıdır).
    """

    degree: int = 2
    alpha: float = 1.0
    _model_x: Pipeline | None = field(default=None, repr=False)
    _model_y: Pipeline | None = field(default=None, repr=False)
    _sample_count: int = 0

    @property
    def is_fitted(self) -> bool:
        return self._model_x is not None and self._model_y is not None

    @property
    def sample_count(self) -> int:
        return self._sample_count

    def fit(self, samples: list[CalibrationSample]) -> None:
        """Toplanan örneklerle modeli eğitir.

        Raises:
            CalibrationError: Örnek sayısı yetersizse veya boyutlar tutarsızsa.
        """
        if len(samples) < 12:
            raise CalibrationError(
                f"En az 12 kalibrasyon örneği gerekiyor, {len(samples)} tane var. "
                "Kullanıcı noktalara yeterince uzun baktı mı?"
            )

        features = np.array([s.features for s in samples], dtype=np.float64)
        if features.ndim != 2:
            raise CalibrationError("Öznitelik vektörlerinin boyutları tutarsız.")

        targets_x = np.array([s.target_x for s in samples], dtype=np.float64)
        targets_y = np.array([s.target_y for s in samples], dtype=np.float64)

        self._model_x = _build_model(self.degree, self.alpha).fit(features, targets_x)
        self._model_y = _build_model(self.degree, self.alpha).fit(features, targets_y)
        self._sample_count = len(samples)

    def predict(self, features: list[float] | np.ndarray) -> tuple[float, float]:
        """Tek bir öznitelik vektöründen normalize bakış konumu.

        Raises:
            CalibrationError: Model henüz eğitilmemişse.
        """
        if self._model_x is None or self._model_y is None:
            raise CalibrationError("Model eğitilmeden tahmin istendi. Önce kalibrasyon yapın.")

        row = np.asarray(features, dtype=np.float64).reshape(1, -1)
        x = float(self._model_x.predict(row)[0])
        y = float(self._model_y.predict(row)[0])
        return float(np.clip(x, 0.0, 1.0)), float(np.clip(y, 0.0, 1.0))

    def evaluate(
        self,
        samples: list[CalibrationSample],
        screen_width_px: int,
        screen_height_px: int,
        screen_width_cm: float,
        distance_cm: float,
    ) -> CalibrationReport:
        """Doğrulama örnekleriyle hatayı ölçer.

        Doğrulama noktaları kalibrasyon ızgarasına denk gelmemelidir; aksi
        halde ölçülen şey ezberdir.
        """
        if not samples:
            raise CalibrationError("Doğrulama için örnek verilmedi.")

        errors_px: list[float] = []
        for sample in samples:
            px, py = self.predict(sample.features)
            dx = (px - sample.target_x) * screen_width_px
            dy = (py - sample.target_y) * screen_height_px
            errors_px.append(math.hypot(dx, dy))

        mean_px = float(np.mean(errors_px))
        cm_per_px = screen_width_cm / screen_width_px if screen_width_px else 0.0
        mean_deg = math.degrees(math.atan2(mean_px * cm_per_px, distance_cm))

        return CalibrationReport(
            sample_count=self._sample_count,
            mean_error_px=mean_px,
            mean_error_deg=mean_deg,
            per_point_error_px=errors_px,
        )


def pixels_to_degrees(
    error_px: float, screen_width_px: int, width_cm: float, distance_cm: float
) -> float:
    """Piksel hatasını görme açısı derecesine çevirir.

    Ekran mesafesi sabit olmadan bu dönüşüm anlamsızdır; ölçüm oturumlarında
    çene desteği kullanın.
    """
    if screen_width_px <= 0 or distance_cm <= 0:
        return 0.0
    cm = error_px * (width_cm / screen_width_px)
    return math.degrees(math.atan2(cm, distance_cm))
