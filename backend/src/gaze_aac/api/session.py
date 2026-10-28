"""Tek bir kullanıcı oturumunun durumu.

Her WebSocket bağlantısı bir oturumdur ve kendi kalibrasyon modelini,
yumuşatıcısını ve dwell sayacını taşır. Durum sunucuda tutulur çünkü
kalibrasyon modeli scikit-learn nesnesidir ve tarayıcıya taşınamaz.

Oturum nesnesi bilerek "aptal" tutuldu: iş mantığı ``gaze`` ve ``nlp``
paketlerinde, burada yalnızca bağlanma var. Böylece aynı mantık simülasyonda
WebSocket olmadan da koşuyor.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from ..config import Settings
from ..gaze.calibration import CalibrationError, GazeMapper
from ..gaze.dwell import DwellDetector, DwellEvent
from ..gaze.filters import GazeSmoother
from ..schemas.gaze import CalibrationReport, CalibrationSample, GazeTarget
from ..schemas.study import StudyBlock
from ..study.recorder import SessionRecorder
from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GazeSession:
    """Bir kullanıcının canlı oturumu."""

    settings: Settings
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    screen_width: int = 1920
    screen_height: int = 1080
    participant_id: str | None = None

    mapper: GazeMapper = field(default_factory=GazeMapper)
    smoother: GazeSmoother = field(init=False)
    dwell: DwellDetector = field(init=False)
    calibration_samples: list[CalibrationSample] = field(default_factory=list)

    # Kullanıcı testi. Kayıt yalnızca ``study_start`` ile açılır; serbest
    # kullanımda hiçbir şey diske yazılmaz.
    recorder: SessionRecorder | None = None
    study_plan: list[StudyBlock] = field(default_factory=list)
    # Son genişletmenin geçerli adayları, arayüzdeki sırayla. Söylenen
    # cümlenin listede kaçıncı olduğu buradan bulunur.
    last_candidates: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.smoother = GazeSmoother(window=self.settings.smoothing_window)
        self.dwell = DwellDetector(
            dwell_ms=self.settings.dwell_ms,
            cancel_grace_ms=self.settings.dwell_cancel_ms,
        )

    # -- Kalibrasyon ------------------------------------------------------

    def add_calibration_sample(
        self, features: list[float], target_x: float, target_y: float
    ) -> None:
        self.calibration_samples.append(
            CalibrationSample(features=features, target_x=target_x, target_y=target_y)
        )

    def fit_calibration(self) -> CalibrationReport:
        """Toplanan örneklerle modeli eğitir ve hatayı ölçer.

        Raises:
            CalibrationError: Örnek yetersizse.
        """
        self.mapper.fit(self.calibration_samples)
        # Not: burada eğitim kümesiyle değerlendirme yapılıyor; gerçek hata
        # ölçümü, ızgaraya denk gelmeyen doğrulama noktalarıyla arayüzün
        # gönderdiği ayrı örnekler üzerinden yapılmalı.
        return self.mapper.evaluate(
            self.calibration_samples,
            screen_width_px=self.screen_width,
            screen_height_px=self.screen_height,
            screen_width_cm=self.settings.screen_width_cm,
            distance_cm=self.settings.screen_distance_cm,
        )

    def reset_calibration(self) -> None:
        self.calibration_samples.clear()
        self.mapper = GazeMapper()
        self.smoother.reset()
        self.dwell.reset()

    # -- Bakış akışı ------------------------------------------------------

    def set_targets(self, targets: list[GazeTarget]) -> None:
        self.dwell.set_targets(targets)

    def process_gaze(self, x: float, y: float, t: float) -> tuple[float, float, DwellEvent]:
        """Ham bakış örneğini yumuşatır ve dwell durumunu günceller.

        Kalibrasyon modeli varsa ve istemci öznitelik gönderiyorsa eşleme
        burada yapılır; ``mouse`` kaynağında istemci zaten ekran koordinatı
        gönderdiği için eşleme atlanır.
        """
        sx, sy = self.smoother.smooth(x, y, t)
        event = self.dwell.update(sx, sy, t)
        return sx, sy, event

    def map_features(self, features: list[float]) -> tuple[float, float]:
        """Öznitelik vektöründen bakış konumu.

        Raises:
            CalibrationError: Model eğitilmemişse.
        """
        return self.mapper.predict(features)

    @property
    def is_calibrated(self) -> bool:
        return self.mapper.is_fitted

    # -- Deney kaydı ------------------------------------------------------

    def log(self, event: str, **fields: object) -> None:
        """Kayıt açıksa olayı yazar, değilse hiçbir şey yapmaz."""
        if self.recorder is not None:
            self.recorder.record(event, **fields)

    def stop_recording(self) -> None:
        if self.recorder is not None:
            self.recorder.close()
            self.recorder = None

    def candidate_rank(self, text: str) -> int | None:
        """Söylenen cümle son aday listesinde kaçıncıydı (0 tabanlı); yoksa ``None``."""
        try:
            return self.last_candidates.index(text)
        except ValueError:
            return None


class SessionRegistry:
    """Açık oturumları tutar.

    Tek süreçli geliştirme sunucusu için yeterli. Çok süreçli dağıtım
    gerekirse buranın Redis gibi paylaşılan bir depoya taşınması gerekir —
    ama bu projenin kapsamında değil.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, GazeSession] = {}

    def create(self, settings: Settings, **kwargs: object) -> GazeSession:
        session = GazeSession(settings=settings, **kwargs)  # type: ignore[arg-type]
        self._sessions[session.session_id] = session
        logger.info("Oturum açıldı: %s", session.session_id)
        return session

    def get(self, session_id: str) -> GazeSession | None:
        return self._sessions.get(session_id)

    def remove(self, session_id: str) -> None:
        if self._sessions.pop(session_id, None) is not None:
            logger.info("Oturum kapandı: %s", session_id)

    def __len__(self) -> int:
        return len(self._sessions)


__all__ = ["CalibrationError", "GazeSession", "SessionRegistry"]
