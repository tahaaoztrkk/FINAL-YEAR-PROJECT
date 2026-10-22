"""MediaPipe yüz landmark modelini indirir.

    python scripts/download_model.py

Model dosyası ~3 MB'dir ve repoya konmaz.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gaze_aac.gaze.landmarks import DEFAULT_MODEL_PATH, MODEL_URL


def main() -> None:
    target = DEFAULT_MODEL_PATH
    if target.exists():
        print(f"Zaten var: {target}")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"İndiriliyor: {MODEL_URL}")
    urllib.request.urlretrieve(MODEL_URL, target)
    print(f"Yazıldı: {target} ({target.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
