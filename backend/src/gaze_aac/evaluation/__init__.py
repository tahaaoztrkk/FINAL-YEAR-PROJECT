"""Değerlendirme: ölçütler ve çevrimdışı simülasyon.

``simulate`` burada içe aktarılmaz: ``python -m gaze_aac.evaluation.simulate``
ile çalıştırıldığında modül iki kez yüklenmiş olur ve Python uyarı verir.
Simülasyon sınıfları doğrudan alt modülden alınır.
"""

from .metrics import (
    SimulationStats,
    character_count,
    keystroke_savings_rate,
    mean_reciprocal_rank,
    theoretical_savings,
    top_k_accuracy,
)

__all__ = [
    "SimulationStats",
    "character_count",
    "keystroke_savings_rate",
    "mean_reciprocal_rank",
    "theoretical_savings",
    "top_k_accuracy",
]
