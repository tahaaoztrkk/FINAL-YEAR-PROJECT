"""Değerlendirme ölçütleri.

Tanımlar raporda aynen kullanılacağı için burada tek yerde tutuluyor; iki
farklı betikte iki farklı KSR tanımı olması, bitirme projelerinde sonuçların
en sık çöptüğü yerdir.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..nlp.schemes import AbbreviationScheme, tokenize


def keystroke_savings_rate(total_selections: int, total_characters: int) -> float:
    """Tuş tasarruf oranı, yüzde.

    KSR = (1 - yapılan_seçim / harf_harf_yazsaydı_gereken_seçim) * 100

    Payda, cümleyi harf harf yazmanın maliyetidir: her karakter bir seçim.
    """
    if total_characters <= 0:
        return 0.0
    return (1.0 - total_selections / total_characters) * 100.0


def character_count(sentence: str) -> int:
    """Cümleyi harf harf yazmanın maliyeti (boşluklar hariç)."""
    return sum(len(word) for word in tokenize(sentence))


def top_k_accuracy(ranks: list[int | None], k: int) -> float:
    """İlk k doğruluk, yüzde.

    Args:
        ranks: Her cümle için doğru adayın sırası (0 tabanlı), bulunamadıysa None.
        k: Kaç aday gösteriliyor.
    """
    if not ranks:
        return 0.0
    hits = sum(1 for rank in ranks if rank is not None and rank < k)
    return hits / len(ranks) * 100.0


def mean_reciprocal_rank(ranks: list[int | None]) -> float:
    """Ortalama karşılıklı sıra.

    İlk-k doğruluktan farkı: doğru adayın listenin neresinde olduğunu da
    hesaba katar. İkinci sıradaki aday, beşinci sıradakinden iyidir.
    """
    if not ranks:
        return 0.0
    return sum(0.0 if rank is None else 1.0 / (rank + 1) for rank in ranks) / len(ranks)


@dataclass
class SimulationStats:
    """Tek bir koşulun (şema x model x bağlam) toplu sonucu."""

    scheme: str
    provider: str
    with_context: bool
    sentence_count: int = 0
    total_selections: int = 0
    total_characters: int = 0
    ranks: list[int | None] = field(default_factory=list)
    latencies_ms: list[float] = field(default_factory=list)

    @property
    def ksr(self) -> float:
        return keystroke_savings_rate(self.total_selections, self.total_characters)

    @property
    def top1(self) -> float:
        return top_k_accuracy(self.ranks, 1)

    @property
    def top5(self) -> float:
        return top_k_accuracy(self.ranks, 5)

    @property
    def mrr(self) -> float:
        return mean_reciprocal_rank(self.ranks)

    @property
    def mean_latency_ms(self) -> float:
        return sum(self.latencies_ms) / len(self.latencies_ms) if self.latencies_ms else 0.0

    def as_row(self) -> dict[str, float | str | int | bool]:
        """CSV satırı. Sütun adları rapordaki tablo başlıklarıyla aynı."""
        return {
            "sema": self.scheme,
            "saglayici": self.provider,
            "baglam": self.with_context,
            "cumle_sayisi": self.sentence_count,
            "ksr": round(self.ksr, 2),
            "ilk1": round(self.top1, 2),
            "ilk5": round(self.top5, 2),
            "mrr": round(self.mrr, 4),
            "gecikme_ms": round(self.mean_latency_ms, 1),
        }


def theoretical_savings(scheme: AbbreviationScheme, sentences: list[str]) -> float:
    """Şemanın üst sınır tasarrufu: her genişletme ilk denemede doğru olsaydı.

    Gerçek KSR bunun altında kalır. Aradaki fark, dil modelinin ne kadar
    iyileştirme alanı bıraktığını gösterir.
    """
    selections = sum(scheme.keystrokes(s) for s in sentences)
    characters = sum(character_count(s) for s in sentences)
    return keystroke_savings_rate(selections, characters)
