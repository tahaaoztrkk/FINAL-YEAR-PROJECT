"""Öznitelik vektöründen ekran koordinatına eşleme.

Kalibrasyon verisi küçüktür (9 nokta x ~30 kare), bu yüzden derin ağ değil
düzenlileştirilmiş regresyon kullanılır.

10 Kasım ölçümleri (docs/haftalik-plan-2026-11-13.md, bölüm 3) üç şeyi
gösterdi ve model ona göre kuruldu:

- 1. derece model 2. dereceden iyi: doğrulama noktalarında 1,8–3,3° yerine
  4,1–8,6°. 2. derece küçük veriyi ezberliyor.
- Baş öznitelikleri (yaw, pitch) kalibrasyonda hiç değişmezse StandardScaler
  onları neredeyse sıfır sapmaya böler; küçük bir baş hareketi tahmini ekran
  dışına fırlatır (~18°). Bu yüzden yalnızca kalibrasyon sırasında baş gerçekten
  oynadıysa modele girerler; o zaman hatayı 2,3–4,5°'ye indiriyorlar.
- Kırpış karelerinde iris noktası aşağı kayar; bu kareler modele girmemeli.

``FEATURE_NAMES`` sırası değişmez: istemci hep 12 sayı gönderir, model hangi
sütunları kullandığını kendisi seçer.

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
from .features import FEATURE_DIM, FEATURE_NAMES

# Her zaman kullanılan sütunlar: dört iris konumu ve iki göz açıklığı.
EYE_FEATURES: tuple[str, ...] = (
    "left_iris_rel_x",
    "left_iris_rel_y",
    "right_iris_rel_x",
    "right_iris_rel_y",
    "left_eye_openness",
    "right_eye_openness",
)
# Yalnızca kalibrasyonda yeterince değiştilerse kullanılanlar.
HEAD_FEATURES: tuple[str, ...] = ("head_yaw", "head_pitch")

_OPENNESS = (FEATURE_NAMES.index("left_eye_openness"), FEATURE_NAMES.index("right_eye_openness"))

MIN_SAMPLES = 12

# features.py'deki güven = min(açıklık) / 0.2; ?bakis güveni 0.3'ün altındaki
# kareleri hiç toplamıyor. Sunucuya her kare gelebileceği için aynı alt sınır
# burada mutlak eşik olarak uygulanır: örneklerin çoğu kapalı gözle gelse bile
# (medyan da kapalıya düşer) bu kareler elenir.
MIN_OPENNESS = 0.3 * 0.2


def blink_threshold(samples: list[CalibrationSample]) -> float:
    """Kırpış sayılacak göz açıklığı eşiği.

    frontend gazeLinear.ts ``blinkThreshold`` ile aynı kural: ekranın alt
    kısmına bakarken göz doğal olarak kısılır, eşik o örneklerin medyanından
    alınır ki aşağı bakış kırpış sanılmasın. Altında ``MIN_OPENNESS`` var.
    """
    bottom = [s for s in samples if s.target_y >= 0.85]
    reference = bottom or samples
    relative = 0.85 * float(np.median([_openness(s.features) for s in reference]))
    return max(relative, MIN_OPENNESS)


def _openness(features: list[float] | np.ndarray) -> float:
    return (float(features[_OPENNESS[0]]) + float(features[_OPENNESS[1]])) / 2.0


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

    Args:
        degree: Polinom derecesi. Ölçümlerde 1 en iyisi; 2 karşılaştırma için.
        alpha: Ridge düzenlileştirmesi.
        head_min_spread: Bir baş özniteliğinin modele girmesi için
            kalibrasyon örneklerindeki %5–%95 aralığının en az bu kadar olması
            gerekir. 0.03 kabaca 4–5°'lik baş dönüşü; ölçümlerle ayarlanacak.
        filter_blinks: Kırpış örneklerini eğitimden çıkar.
    """

    degree: int = 1
    alpha: float = 1.0
    head_min_spread: float = 0.03
    filter_blinks: bool = True
    _model_x: Pipeline | None = field(default=None, repr=False)
    _model_y: Pipeline | None = field(default=None, repr=False)
    _columns: tuple[int, ...] = field(default=(), repr=False)
    _head_range: dict[int, tuple[float, float]] = field(default_factory=dict, repr=False)
    _sample_count: int = 0
    _discarded_blinks: int = 0

    @property
    def is_fitted(self) -> bool:
        return self._model_x is not None and self._model_y is not None

    @property
    def sample_count(self) -> int:
        """Modelin eğitildiği örnek sayısı (kırpışlar çıkarıldıktan sonra)."""
        return self._sample_count

    @property
    def discarded_blinks(self) -> int:
        return self._discarded_blinks

    @property
    def feature_names(self) -> tuple[str, ...]:
        """Modelin kullandığı öznitelikler; kayıt ve rapor için."""
        return tuple(FEATURE_NAMES[i] for i in self._columns)

    @property
    def uses_head_pose(self) -> bool:
        return bool(self._head_range)

    def fit(self, samples: list[CalibrationSample]) -> None:
        """Toplanan örneklerle modeli eğitir.

        Raises:
            CalibrationError: Örnek sayısı yetersizse veya boyutlar tutarsızsa.
        """
        if len(samples) < MIN_SAMPLES:
            raise CalibrationError(
                f"En az {MIN_SAMPLES} kalibrasyon örneği gerekiyor, {len(samples)} tane var. "
                "Kullanıcı noktalara yeterince uzun baktı mı?"
            )
        if any(len(s.features) != FEATURE_DIM for s in samples):
            raise CalibrationError(
                f"Her örnekte {FEATURE_DIM} öznitelik olmalı (FEATURE_NAMES). "
                "İstemci features.py ile aynı vektörü mü gönderiyor?"
            )

        kept = samples
        if self.filter_blinks:
            threshold = blink_threshold(samples)
            kept = [s for s in samples if _openness(s.features) >= threshold]
            if len(kept) < MIN_SAMPLES:
                raise CalibrationError(
                    f"Kırpışlar çıkarılınca {len(kept)} örnek kaldı, "
                    f"en az {MIN_SAMPLES} gerekiyor. Gözler kalibrasyon sırasında açık mıydı?"
                )

        features = np.array([s.features for s in kept], dtype=np.float64)
        targets_x = np.array([s.target_x for s in kept], dtype=np.float64)
        targets_y = np.array([s.target_y for s in kept], dtype=np.float64)

        columns = [FEATURE_NAMES.index(name) for name in EYE_FEATURES]
        head_range: dict[int, tuple[float, float]] = {}
        for name in HEAD_FEATURES:
            index = FEATURE_NAMES.index(name)
            column = features[:, index]
            low, high = np.percentile(column, [5, 95])
            if high - low >= self.head_min_spread:
                columns.append(index)
                head_range[index] = (float(np.min(column)), float(np.max(column)))

        selected = features[:, columns]
        model_x = _build_model(self.degree, self.alpha).fit(selected, targets_x)
        model_y = _build_model(self.degree, self.alpha).fit(selected, targets_y)

        self._model_x, self._model_y = model_x, model_y
        self._columns = tuple(columns)
        self._head_range = head_range
        self._sample_count = len(kept)
        self._discarded_blinks = len(samples) - len(kept)

    def predict(self, features: list[float] | np.ndarray) -> tuple[float, float]:
        """Tek bir öznitelik vektöründen normalize bakış konumu.

        Raises:
            CalibrationError: Model henüz eğitilmemişse veya vektör boyu yanlışsa.
        """
        if self._model_x is None or self._model_y is None:
            raise CalibrationError("Model eğitilmeden tahmin istendi. Önce kalibrasyon yapın.")

        row = np.asarray(features, dtype=np.float64).reshape(-1)
        if row.shape[0] != FEATURE_DIM:
            raise CalibrationError(f"{FEATURE_DIM} öznitelik bekleniyordu, {row.shape[0]} geldi.")
        selected = row[list(self._columns)].reshape(1, -1)
        x = float(self._model_x.predict(selected)[0])
        y = float(self._model_y.predict(selected)[0])
        return float(np.clip(x, 0.0, 1.0)), float(np.clip(y, 0.0, 1.0))

    def in_calibrated_pose(self, features: list[float] | np.ndarray, margin: float = 0.0) -> bool:
        """Baş, kalibrasyonda görülen yaw/pitch aralığında mı?

        Aralık dışında doğrusal model yalnızca uydurur; çağıran taraf (ws)
        imleci tutup kullanıcıyı uyarabilir (?bakis sayfasındaki gibi). Baş
        öznitelikleri modele girmediyse hep ``True``.
        """
        for index, (low, high) in self._head_range.items():
            value = float(features[index])
            if value < low - margin or value > high + margin:
                return False
        return True

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
