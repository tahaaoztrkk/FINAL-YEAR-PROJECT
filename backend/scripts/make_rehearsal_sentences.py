"""Prova ve pilot için ayrı bir cümle seti üretir.

    python scripts/make_rehearsal_sentences.py > ../data/study/prova_sentences.json

Kullanıcı testi yalnızca ekip üyeleriyle yapıldığı için prova ve pilot da
bir ekip üyesiyle yapılır. Provada asıl deney cümleleri (sentences.json)
kullanılırsa o kişi kendi K oturumundan önce ölçülecek cümleleri görür.
Bu betik, asıl dosyayla aynı yapıda (2+2 alıştırma, 2×10 ölçülen) bir
prova seti seçer:

- yalnızca derlemin eğitim kısmından,
- her asıl cümle için kelime sayısı aynı, uzunluğu yakın bir cümle,
- asıl deney cümleleriyle 4 ya da daha uzun harfli ortak kelimesi olmayan.

Tohum sabittir; aynı derlemle her çalıştırmada aynı dosya çıkar.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gaze_aac.data.corpus import Corpus
from gaze_aac.nlp.schemes import tokenize

REPO = Path(__file__).resolve().parents[2]
SEED = 20261121
MIN_SHARED_LEN = 4


def main() -> None:
    study = json.loads((REPO / "data/study/sentences.json").read_text(encoding="utf-8"))
    study_all = (
        study["practice"]["A"] + study["practice"]["B"] + study["sets"][0] + study["sets"][1]
    )
    study_tokens = {t for s in study_all for t in tokenize(s) if len(t) >= MIN_SHARED_LEN}

    train = Corpus.load(REPO / "data/corpus/aac_sentences.jsonl").split()[0].entries
    pool: list[tuple[str, int, int]] = []
    seen: set[str] = set()
    for entry in train:
        text = entry.text.strip()
        tokens = tokenize(text)
        normalized = " ".join(tokens)
        if not tokens or normalized in seen or not text.endswith((".", "?", "!")):
            continue
        if any(len(t) >= MIN_SHARED_LEN and t in study_tokens for t in tokens):
            continue
        seen.add(normalized)
        pool.append((text, len(tokens), len(normalized)))

    random.Random(SEED).shuffle(pool)
    used: set[int] = set()

    def match(sentence: str) -> str:
        tokens = tokenize(sentence)
        n_words, n_chars = len(tokens), len(" ".join(tokens))
        for tolerance in (2, 3, 5, 8):
            for i, (text, words, chars) in enumerate(pool):
                if i in used:
                    continue
                if (
                    words == n_words
                    and abs(chars - n_chars) <= tolerance
                    and text.endswith(sentence[-1])
                ):
                    used.add(i)
                    return text
        for i, (text, words, _) in enumerate(pool):
            if i not in used and words == n_words:
                used.add(i)
                return text
        raise SystemExit(f"Eşleşen cümle bulunamadı: {sentence!r}")

    out = {
        "aciklama": (
            "PROVA ve PİLOT içindir; asıl K oturumlarında KULLANILMAZ. Derlemin eğitim kısmından, "
            "deney cümleleriyle 4+ harfli ortak kelimesi olmayan ve her deney cümlesiyle kelime "
            f"sayısı/uzunluk bakımından eşleşen cümleler (seçim betiği: tohum {SEED})."
        ),
        "scheme": study["scheme"],
        "practice": {
            "A": [match(s) for s in study["practice"]["A"]],
            "B": [match(s) for s in study["practice"]["B"]],
        },
        "sets": [[match(s) for s in block] for block in study["sets"]],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
