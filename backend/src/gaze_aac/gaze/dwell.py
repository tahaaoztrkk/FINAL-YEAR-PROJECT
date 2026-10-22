"""Bakışla seçim (dwell) mantığı.

Midas touch problemi: göz sadece bakmak için de hareket eder, ama her bakış
seçim sayılırsa kullanıcı istemediği tuşlara basar. Çözüm, seçimi bir süre
eşiğine bağlamak ve bakış ayrıldığında ilerlemeyi geri almak.

İlerleme anında sıfırlanmaz: kısa bir tolerans süresi vardır, çünkü bakış
tahmininin doğal titremesi hedefin kenarında dolaşırken ilerlemeyi sürekli
sıfırlar ve seçim hiç tamamlanmaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..schemas.gaze import GazeTarget


@dataclass(frozen=True)
class DwellEvent:
    """Bir bakış örneğinin dwell durumuna etkisi."""

    target_id: str | None
    progress: float
    selected: bool
    elapsed_ms: float = 0.0


@dataclass
class DwellDetector:
    """Hedefler üstünde biriken bakış süresini izler.

    Args:
        dwell_ms: Seçim için gereken toplam süre.
        cancel_grace_ms: Bakış hedeften ayrıldıktan sonra ilerlemenin
            korunduğu süre. Bu süre dolmadan geri dönülürse sayaç kaldığı
            yerden devam eder.
        refractory_ms: Bir seçimden sonra yeni seçimin engellendiği süre.
            Kullanıcının bakışını çekmesine zaman tanır, çift seçimi önler.
    """

    dwell_ms: int = 700
    cancel_grace_ms: int = 150
    refractory_ms: int = 300

    _targets: list[GazeTarget] = field(default_factory=list, repr=False)
    _active_id: str | None = field(default=None, repr=False)
    _accumulated_ms: float = field(default=0.0, repr=False)
    _last_t: float | None = field(default=None, repr=False)
    _away_ms: float = field(default=0.0, repr=False)
    _refractory_left_ms: float = field(default=0.0, repr=False)

    def set_targets(self, targets: list[GazeTarget]) -> None:
        """Ekran düzeni değiştiğinde çağrılır; biriken ilerleme sıfırlanır."""
        self._targets = list(targets)
        self.reset_progress()

    def reset_progress(self) -> None:
        self._active_id = None
        self._accumulated_ms = 0.0
        self._away_ms = 0.0

    def reset(self) -> None:
        self.reset_progress()
        self._last_t = None
        self._refractory_left_ms = 0.0

    def _hit_test(self, x: float, y: float) -> GazeTarget | None:
        # Üst üste binen hedeflerde en küçüğü kazanır: iç içe düzenlerde
        # kullanıcının daha hassas olanı kastettiği varsayılır.
        hits = [t for t in self._targets if t.contains(x, y)]
        if not hits:
            return None
        return min(hits, key=lambda t: t.width * t.height)

    def update(self, x: float, y: float, t: float) -> DwellEvent:
        """Yeni bakış örneğini işler ve güncel dwell durumunu döner.

        Args:
            x, y: Normalize bakış konumu.
            t: Zaman damgası, saniye.
        """
        if self._last_t is None:
            self._last_t = t
            return DwellEvent(target_id=None, progress=0.0, selected=False)

        dt_ms = max(0.0, (t - self._last_t) * 1000.0)
        self._last_t = t

        if self._refractory_left_ms > 0.0:
            self._refractory_left_ms = max(0.0, self._refractory_left_ms - dt_ms)
            return DwellEvent(target_id=None, progress=0.0, selected=False)

        hit = self._hit_test(x, y)

        if hit is None:
            # Bakış boşlukta: tolerans süresi dolana kadar ilerlemeyi koru.
            self._away_ms += dt_ms
            if self._away_ms > self.cancel_grace_ms:
                self.reset_progress()
            return DwellEvent(
                target_id=self._active_id,
                progress=self._progress(),
                selected=False,
            )

        if hit.id != self._active_id:
            self._active_id = hit.id
            self._accumulated_ms = 0.0

        self._away_ms = 0.0
        self._accumulated_ms += dt_ms

        if self._accumulated_ms >= self.dwell_ms:
            elapsed = self._accumulated_ms
            selected_id = hit.id
            self.reset_progress()
            self._refractory_left_ms = float(self.refractory_ms)
            return DwellEvent(
                target_id=selected_id, progress=1.0, selected=True, elapsed_ms=elapsed
            )

        return DwellEvent(target_id=hit.id, progress=self._progress(), selected=False)

    def _progress(self) -> float:
        if self.dwell_ms <= 0:
            return 0.0
        return min(1.0, self._accumulated_ms / self.dwell_ms)
