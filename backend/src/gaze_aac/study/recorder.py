"""Oturum kaydı.

Kullanıcı testinde olan her şey zaman damgasıyla tek bir JSONL dosyasına
yazılır: hedef cümle, seçimler, genişletme istekleri ve adaylar, söylenen
cümle, bakış konumu. Analiz betiği yalnızca bu dosyayı okur; deney sırasında
kâğıda ölçüm tutulmaz.

KVKK: kamera görüntüsü ve 478 noktalı yüz ağı hiçbir zaman yazılmaz. Bakış
için ekran konumu, kalibrasyon için yalnızca öznitelik vektörü kaydedilir.
Kayıtlar deney bilgisayarında kalır; ``data/sessions/`` repoya girmez.

Dosya satır tamponludur: tarayıcı çökse ya da elektrik gitse bile o ana
kadarki olaylar diskte olur.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import TextIO

# Öznitelik vektörü 12 boyutlu. Yüz ağı 478 x 3 = 1434 sayıdır; sınır ikisini
# rahatça ayırır ve vektör büyürse diye pay bırakır.
MAX_RECORDED_FEATURES = 32


def loggable_features(features: Sequence[float]) -> list[float] | None:
    """Kaydedilebilecek öznitelik vektörü; yüz ağı gibi görünüyorsa ``None``.

    Sınır kaydın kapısında konur: arayüz yanlışlıkla ham noktaları öznitelik
    diye gönderse bile diske düşmez.
    """
    if len(features) > MAX_RECORDED_FEATURES:
        return None
    return [round(float(value), 5) for value in features]


class SessionRecorder:
    """Bir bağlantının deney kaydı. Her satır bir olay."""

    def __init__(self, path: Path, clock: Callable[[], float] = time.monotonic) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._clock = clock
        self._started = clock()
        self._handle: TextIO | None = path.open("a", encoding="utf-8", buffering=1)

    @classmethod
    def create(
        cls,
        sessions_dir: Path,
        participant_id: str,
        session_id: str,
        now: datetime | None = None,
    ) -> SessionRecorder:
        """``<sessions_dir>/<katılımcı>/<tarih-saat>_<oturum>.jsonl``.

        Bağlantı koparsa yeni bağlantı yeni dosya açar; analiz bir
        katılımcının bütün dosyalarını birlikte okur.
        """
        stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
        return cls(sessions_dir / participant_id / f"{stamp}_{session_id}.jsonl")

    @property
    def closed(self) -> bool:
        return self._handle is None

    def elapsed(self) -> float:
        """Kayıt başından beri geçen süre, saniye. Duvar saati değil: geri atlamaz."""
        return self._clock() - self._started

    def record(self, event: str, **fields: object) -> None:
        """Bir olay satırı yazar. Kapalı kayda yazmak sessizce yok sayılır."""
        if self._handle is None:
            return
        line = {"t": round(self.elapsed(), 4), "event": event, **fields}
        self._handle.write(json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n")

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
