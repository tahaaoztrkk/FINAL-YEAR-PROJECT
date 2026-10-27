"""N-gram taban çizgisi.

Raporun karşılaştırma tablosunda "dil modeli olmasaydı ne olurdu" sorusunun
cevabı bu. Kelime düzeyinde bigram sayımıyla, kısaltmaya uyan kelime
dizilerini üretir.

Bilinçli olarak basit: amacı iyi çalışmak değil, dil modelinin ne kadar
katkı sağladığını ölçmek.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from ...schemas.expansion import Candidate, ExpansionRequest
from ..schemes import get_scheme, normalize_abbreviation, tokenize, turkish_capitalize


class NGramProvider:
    """Bigram sayımlarıyla ışın aramalı genişletme."""

    name = "ngram"

    def __init__(self, corpus_path: Path | None = None, beam_width: int = 20) -> None:
        self.beam_width = beam_width
        self._unigram: Counter[str] = Counter()
        self._bigram: dict[str, Counter[str]] = defaultdict(Counter)
        self._by_abbrev: dict[str, dict[str, list[str]]] = {}
        # Kelime dizisi derlemdeki bir cümleyle birebir aynıysa, noktalaması
        # ve yazımı korunmuş özgün hali gösterilir.
        self._originals: dict[tuple[str, ...], str] = {}
        if corpus_path is not None and corpus_path.exists():
            self.fit_from_file(corpus_path)

    def fit(self, sentences: list[str]) -> None:
        """Derlemden sayımları çıkarır."""
        for sentence in sentences:
            words = tokenize(sentence)
            self._originals.setdefault(tuple(words), sentence.strip())
            previous = "<s>"
            for word in words:
                self._unigram[word] += 1
                self._bigram[previous][word] += 1
                previous = word
            self._bigram[previous]["</s>"] += 1

        # Her şema için "bu kısaltma parçasına uyan kelimeler" dizini.
        self._by_abbrev = {}
        for scheme in ("S1", "S2", "S3", "S4"):
            handler = get_scheme(scheme)
            index: dict[str, list[str]] = defaultdict(list)
            for word in self._unigram:
                # Anahtar normalleştirilir: S4 etiketleri büyük harfle üretilir,
                # sorgu parçaları ise küçültülmüş gelir.
                index[normalize_abbreviation(handler.abbreviate_word(word))].append(word)
            self._by_abbrev[scheme] = dict(index)

    def fit_from_file(self, corpus_path: Path) -> None:
        sentences: list[str] = []
        with corpus_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                text = record.get("text") if isinstance(record, dict) else None
                if isinstance(text, str):
                    sentences.append(text)
        self.fit(sentences)

    def _log_prob(self, previous: str, word: str) -> float:
        """Katkı yumuşatmalı bigram log olasılığı."""
        following = self._bigram.get(previous, Counter())
        total = sum(following.values())
        vocabulary = max(1, len(self._unigram))
        return math.log((following.get(word, 0) + 1) / (total + vocabulary))

    async def expand(self, request: ExpansionRequest) -> list[Candidate]:
        if not self._unigram:
            return []

        scheme_id = request.scheme.upper()
        index = self._by_abbrev.get(scheme_id, {})
        pieces = normalize_abbreviation(request.abbreviation).split()
        if not pieces:
            return []

        # Işın araması: her adımda en olası kısmi diziler tutulur.
        beam: list[tuple[list[str], float]] = [([], 0.0)]
        for piece in pieces:
            options = list(index.get(piece, []))
            # Kullanıcı kelimeyi açık yazdıysa (simülasyonun sonraki turları,
            # ya da adaylar tutmayınca elle yazma) parça kısaltma değil
            # kelimenin kendisidir; derlemde hiç geçmese bile kullanılır.
            # Kısa ya da etiketli parçalar kısaltmadır: "x" tek başına
            # "X istiyorum" gibi anlamsız bir aday üretmemeli.
            spelled_out = piece in self._unigram or (len(piece) > 2 and "-" not in piece)
            if piece not in options and spelled_out:
                options.append(piece)
            if not options:
                return []
            expanded: list[tuple[list[str], float]] = []
            for words, score in beam:
                previous = words[-1] if words else "<s>"
                for option in options:
                    expanded.append(([*words, option], score + self._log_prob(previous, option)))
            beam = sorted(expanded, key=lambda item: -item[1])[: self.beam_width]

        # Adayların hepsi aynı sayıda kelime ama hepsi cümle sonu değil:
        # "Bugün ayın" yarım kalmıştır. Cümle sonu olasılığı bunları geri iter.
        finished = [(words, score + self._log_prob(words[-1], "</s>")) for words, score in beam]
        finished.sort(key=lambda item: -item[1])

        return [
            Candidate(text=self._render(words), score=float(score))
            for words, score in finished[: request.top_k]
        ]

    def _render(self, words: list[str]) -> str:
        original = self._originals.get(tuple(words))
        if original is not None:
            return original
        return turkish_capitalize(" ".join(words))
