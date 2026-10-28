"""İstemci ve sunucu arasındaki WebSocket mesaj sözleşmesi.

Bu dosya sistemin tek doğruluk kaynağıdır. Arayüz ile servis arasındaki her
mesaj burada tanımlıdır; TypeScript karşılıkları ``scripts/export_schema.py``
ile bu modelden üretilir, elle yazılmaz.

Sözleşme değişikliği her iki tarafı da ilgilendirir: değiştiren kişi aynı PR
içinde tipleri yeniden üretip ``docs/ws-protocol.md`` dosyasını güncellemelidir.

Ayrım şu: ``Client*`` mesajları tarayıcıdan sunucuya, ``Server*`` mesajları
sunucudan tarayıcıya gider. ``type`` alanı ayırt edici etikettir.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .expansion import Candidate
from .gaze import GazePoint, GazeTarget
from .study import StudyBlock, StudyTrial


class _Message(BaseModel):
    """Tüm mesajların ortak tabanı."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# --------------------------------------------------------------------------
# İstemci -> Sunucu
# --------------------------------------------------------------------------


class ClientHello(_Message):
    """Bağlantı kurulduğunda gönderilen ilk mesaj."""

    type: Literal["hello"] = "hello"
    screen_width: int = Field(gt=0, description="Ekran genişliği, piksel")
    screen_height: int = Field(gt=0, description="Ekran yüksekliği, piksel")
    participant_id: str | None = Field(
        default=None, description="Deney oturumlarında katılımcı kodu (ör. K07)"
    )


class ClientGazeSample(_Message):
    """Tek bir bakış örneği.

    Arayüz bunu kare hızında (~30 Hz) gönderir. Sunucu yumuşatma ve dwell
    kararını bu akış üzerinden verir.
    """

    type: Literal["gaze"] = "gaze"
    point: GazePoint


class ClientCalibrationSample(_Message):
    """Kalibrasyon sırasında, kullanıcının baktığı bilinen nokta."""

    type: Literal["calibration_sample"] = "calibration_sample"
    target_x: float = Field(ge=0.0, le=1.0, description="Hedefin normalize x konumu")
    target_y: float = Field(ge=0.0, le=1.0, description="Hedefin normalize y konumu")
    features: list[float] = Field(description="Göz/baş öznitelik vektörü")


class ClientCalibrationFit(_Message):
    """Toplanan örneklerle regresyon modelini eğitmeyi ister."""

    type: Literal["calibration_fit"] = "calibration_fit"


class ClientTargets(_Message):
    """Ekrandaki dwell hedeflerinin güncel listesi.

    Arayüz düzeni değiştiğinde (harf grubundan harfe geçiş, aday listesinin
    açılması) yeniden gönderilir.
    """

    type: Literal["targets"] = "targets"
    targets: list[GazeTarget]


class ClientSelect(_Message):
    """Dwell dışında yapılan doğrudan seçim (fare ile geliştirme, erişilebilirlik
    düğmesi veya test otomasyonu)."""

    type: Literal["select"] = "select"
    target_id: str


class ClientExpand(_Message):
    """Kısaltmanın cümleye genişletilmesini ister."""

    type: Literal["expand"] = "expand"
    abbreviation: str = Field(min_length=1, description="Kullanıcının girdiği kısaltma")
    scheme: str = Field(default="S1", description="Kısaltma şeması kimliği")
    context: str | None = Field(default=None, description="Karşı tarafın son cümlesi, varsa")
    top_k: int = Field(default=5, ge=1, le=10)


class ClientSpeak(_Message):
    """Seçilen cümlenin seslendirilmesini bildirir (kayıt ve ölçüm için)."""

    type: Literal["speak"] = "speak"
    text: str


class ClientStudyStart(_Message):
    """Kullanıcı testini başlatır. Sunucu planı kurar ve kaydı açar.

    Bağlantı koparsa istemci yeniden gönderir; kayıt yeni dosyada sürer.
    """

    type: Literal["study_start"] = "study_start"
    participant_id: str = Field(min_length=1, max_length=8, description="Katılımcı kodu (ör. K07)")


class ClientTrialStart(_Message):
    """Hedef cümle ekranda; ölçüm ilk seçimle başlar."""

    type: Literal["trial_start"] = "trial_start"
    block_index: int = Field(ge=0)
    trial_index: int = Field(ge=0)


class ClientTrialEnd(_Message):
    """Cümle doğru söylendi ya da deneyi yürüten kişi atladı."""

    type: Literal["trial_end"] = "trial_end"
    block_index: int = Field(ge=0)
    trial_index: int = Field(ge=0)
    outcome: Literal["done", "skipped"]
    output: str = Field(default="", description="Katılımcının son ürettiği metin")


class ClientStudyEnd(_Message):
    """Son blok bitti; kayıt kapanır."""

    type: Literal["study_end"] = "study_end"


ClientMessage = Annotated[
    ClientHello
    | ClientGazeSample
    | ClientCalibrationSample
    | ClientCalibrationFit
    | ClientTargets
    | ClientSelect
    | ClientExpand
    | ClientSpeak
    | ClientStudyStart
    | ClientTrialStart
    | ClientTrialEnd
    | ClientStudyEnd,
    Field(discriminator="type"),
]


# --------------------------------------------------------------------------
# Sunucu -> İstemci
# --------------------------------------------------------------------------


class ServerReady(_Message):
    """Bağlantı hazır; sunucunun etkin yapılandırmasını bildirir."""

    type: Literal["ready"] = "ready"
    session_id: str
    gaze_source: str
    expander_provider: str
    dwell_ms: int


class ServerGaze(_Message):
    """Yumuşatılmış bakış konumu. Arayüz imleci bununla çizer."""

    type: Literal["gaze"] = "gaze"
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    t: float = Field(description="Örneğin zaman damgası, saniye")


class ServerDwellProgress(_Message):
    """Bir hedefin üstünde biriken dwell oranı. Arayüz halkayı bununla doldurur."""

    type: Literal["dwell_progress"] = "dwell_progress"
    target_id: str
    progress: float = Field(ge=0.0, le=1.0)


class ServerSelection(_Message):
    """Dwell tamamlandı, hedef seçildi."""

    type: Literal["selection"] = "selection"
    target_id: str
    dwell_ms: float = Field(description="Seçimin gerçekte ne kadar sürdüğü")


class ServerCalibrationResult(_Message):
    """Kalibrasyon sonucu ve doğrulama hatası."""

    type: Literal["calibration_result"] = "calibration_result"
    ok: bool
    sample_count: int
    mean_error_px: float | None = None
    mean_error_deg: float | None = None
    message: str | None = None


class ServerCandidates(_Message):
    """Kısaltmaya karşılık üretilen aday cümleler."""

    type: Literal["candidates"] = "candidates"
    abbreviation: str
    scheme: str
    candidates: list[Candidate]
    latency_ms: float


class ServerStudyPlan(_Message):
    """Katılımcının deney planı: koşul sırası ve her bloğun cümleleri."""

    type: Literal["study_plan"] = "study_plan"
    participant_id: str = Field(description="Tek biçime getirilmiş kod (k7 -> K07)")
    order: str = Field(description="Koşul sırası, AB ya da BA")
    blocks: list[StudyBlock]


class ServerError(_Message):
    """İşlenemeyen istek. Bağlantı açık kalır."""

    type: Literal["error"] = "error"
    code: str
    detail: str


ServerMessage = Annotated[
    ServerReady
    | ServerGaze
    | ServerDwellProgress
    | ServerSelection
    | ServerCalibrationResult
    | ServerCandidates
    | ServerStudyPlan
    | ServerError,
    Field(discriminator="type"),
]


__all__ = [
    "Candidate",
    "ClientCalibrationFit",
    "ClientCalibrationSample",
    "ClientExpand",
    "ClientGazeSample",
    "ClientHello",
    "ClientMessage",
    "ClientSelect",
    "ClientSpeak",
    "ClientStudyEnd",
    "ClientStudyStart",
    "ClientTargets",
    "ClientTrialEnd",
    "ClientTrialStart",
    "GazePoint",
    "GazeTarget",
    "ServerCalibrationResult",
    "ServerCandidates",
    "ServerDwellProgress",
    "ServerError",
    "ServerGaze",
    "ServerMessage",
    "ServerReady",
    "ServerSelection",
    "ServerStudyPlan",
    "StudyBlock",
    "StudyTrial",
]
