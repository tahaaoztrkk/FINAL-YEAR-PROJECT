"""Bakış verisi ve ekran hedefleriyle ilgili şemalar."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GazePoint(BaseModel):
    """Tek bir bakış örneği.

    Koordinatlar 0–1 aralığında normalize edilir; böylece farklı ekran
    çözünürlükleri arasında taşınabilir olur. Dönüşümü arayüz yapar.
    """

    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    t: float = Field(description="İstemci zaman damgası, saniye")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class GazeTarget(BaseModel):
    """Ekranda bakışla seçilebilen dikdörtgen alan.

    Konum ve boyut normalize edilmiştir. ``kind`` alanı seçimin arayüzde ne
    anlama geldiğini söyler; sunucu bunu yorumlamaz, yalnızca geri bildirir.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    x: float = Field(ge=0.0, le=1.0, description="Sol kenar")
    y: float = Field(ge=0.0, le=1.0, description="Üst kenar")
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)
    label: str = ""
    kind: str = Field(default="key", description="key | group | candidate | action")

    def contains(self, x: float, y: float) -> bool:
        """Verilen normalize nokta bu hedefin içinde mi."""
        return self.x <= x <= self.x + self.width and self.y <= y <= self.y + self.height

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.width / 2, self.y + self.height / 2


class CalibrationSample(BaseModel):
    """Eğitim için tek bir (öznitelik, bilinen hedef) çifti."""

    model_config = ConfigDict(extra="forbid")

    features: list[float]
    target_x: float = Field(ge=0.0, le=1.0)
    target_y: float = Field(ge=0.0, le=1.0)


class CalibrationReport(BaseModel):
    """Kalibrasyon sonrası doğruluk raporu."""

    model_config = ConfigDict(extra="forbid")

    sample_count: int
    mean_error_px: float
    mean_error_deg: float
    per_point_error_px: list[float] = Field(default_factory=list)
