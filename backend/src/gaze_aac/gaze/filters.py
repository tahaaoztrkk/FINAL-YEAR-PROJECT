"""Bakış sinyalini yumuşatma.

Ham tahmin titrer; titreyen imleç küçük hedeflerde seçimi imkânsız kılar.
Ama yumuşatma gecikme ekler ve gecikme de kullanıcıyı yavaşlatır. One Euro
filtresi bu dengeyi uyarlanabilir şekilde kurar: yavaş hareket ederken çok
yumuşatır, hızlı hareket ederken bırakır.

Kaynak: Casiez, Roussel, Vogel, "1C Filter" (CHI 2012).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field


class _LowPass:
    """Tek eksenli üstel yumuşatma."""

    def __init__(self) -> None:
        self._value: float | None = None

    def apply(self, x: float, alpha: float) -> float:
        if self._value is None:
            self._value = x
        else:
            self._value = alpha * x + (1.0 - alpha) * self._value
        return self._value

    @property
    def value(self) -> float | None:
        return self._value

    def reset(self) -> None:
        self._value = None


def _alpha(cutoff: float, dt: float) -> float:
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


@dataclass
class OneEuroFilter:
    """Tek eksen için uyarlanabilir yumuşatma.

    Args:
        min_cutoff: Durağan haldeki kesme frekansı. Düşürmek titremeyi azaltır,
            gecikmeyi artırır.
        beta: Hıza duyarlılık. Artırmak hızlı hareketlerde gecikmeyi azaltır.
        d_cutoff: Hız tahmininin kendi yumuşatması.
    """

    min_cutoff: float = 1.0
    beta: float = 0.007
    d_cutoff: float = 1.0
    _x: _LowPass = field(default_factory=_LowPass, repr=False)
    _dx: _LowPass = field(default_factory=_LowPass, repr=False)
    _last_t: float | None = field(default=None, repr=False)

    def __call__(self, value: float, t: float) -> float:
        if self._last_t is None or t <= self._last_t:
            self._last_t = t
            return self._x.apply(value, 1.0)

        dt = t - self._last_t
        self._last_t = t

        prev = self._x.value if self._x.value is not None else value
        derivative = (value - prev) / dt
        edx = self._dx.apply(derivative, _alpha(self.d_cutoff, dt))

        cutoff = self.min_cutoff + self.beta * abs(edx)
        return self._x.apply(value, _alpha(cutoff, dt))

    def reset(self) -> None:
        self._x.reset()
        self._dx.reset()
        self._last_t = None


@dataclass
class GazeSmoother:
    """İki eksenli bakış yumuşatıcı.

    One Euro varsayılandır. ``window`` verilirse bunun yerine kayan ortalama
    kullanılır; karşılaştırma deneyleri için basit bir taban çizgisidir.
    """

    use_one_euro: bool = True
    window: int = 5
    min_cutoff: float = 1.0
    beta: float = 0.007
    _fx: OneEuroFilter = field(default_factory=OneEuroFilter, repr=False)
    _fy: OneEuroFilter = field(default_factory=OneEuroFilter, repr=False)
    _buf_x: deque[float] = field(default_factory=lambda: deque(maxlen=5), repr=False)
    _buf_y: deque[float] = field(default_factory=lambda: deque(maxlen=5), repr=False)

    def __post_init__(self) -> None:
        self._fx = OneEuroFilter(min_cutoff=self.min_cutoff, beta=self.beta)
        self._fy = OneEuroFilter(min_cutoff=self.min_cutoff, beta=self.beta)
        self._buf_x = deque(maxlen=self.window)
        self._buf_y = deque(maxlen=self.window)

    def smooth(self, x: float, y: float, t: float) -> tuple[float, float]:
        if self.use_one_euro:
            return self._fx(x, t), self._fy(y, t)
        self._buf_x.append(x)
        self._buf_y.append(y)
        return sum(self._buf_x) / len(self._buf_x), sum(self._buf_y) / len(self._buf_y)

    def reset(self) -> None:
        self._fx.reset()
        self._fy.reset()
        self._buf_x.clear()
        self._buf_y.clear()
