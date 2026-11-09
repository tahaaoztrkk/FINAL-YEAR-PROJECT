"""Derlemi hazırlayıp eğitim çiftlerini üreten komut.

    python -m gaze_aac.data.build_corpus
    python -m gaze_aac.data.build_corpus --seed-only

Ham derlem ``data/corpus/aac_sentences.jsonl`` dosyasında, repoda tutulur;
ekip yeni cümleleri bu dosyaya PR ile ekler. İlk komut onu temizler, böler
ve eğitim çiftlerini üretir. ``--seed-only`` yalnızca aşağıdaki küçük
çekirdeği ``data/raw/seed_sentences.jsonl`` dosyasına yazar.

Cümle üretimini bilerek otomatikleştirmedik: doğal olmayan Türkçe cümleler
veri setini sessizce bozar ve dört kişinin 750'şer cümleyi elden geçirmesi,
sonradan sonuçları açıklayamamaktan ucuzdur.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..config import get_settings
from ..study.protocol import StudyMaterials
from .corpus import Corpus, CorpusEntry, build_training_pairs, write_pairs

# Her kategori için başlangıç cümleleri. Ekip bunları 40–50'ye çıkarır,
# sonra bir API modelinden çeşitlendirme ister.
SEED: dict[str, tuple[str, ...]] = {
    "temel_ihtiyac": (
        "Su istiyorum.",
        "Acıktım.",
        "Tuvalete gitmem lazım.",
        "Ağzım kurudu.",
        "Biraz daha su alabilir miyim?",
    ),
    "agri_saglik": (
        "Başım ağrıyor.",
        "Nefes almakta zorlanıyorum.",
        "Sırtım çok ağrıyor.",
        "İlacımın saati geldi.",
        "Doktoru çağırır mısın?",
    ),
    "pozisyon_bakim": (
        "Pozisyonumu değiştirir misin?",
        "Yatağımı yukarı kaldırır mısın?",
        "Üşüyorum, battaniye alır mısın?",
        "Gözlüğümü takar mısın?",
        "Yastığımı düzeltir misin?",
    ),
    "duygu": (
        "Bugün kendimi iyi hissediyorum.",
        "Çok yorgunum.",
        "Seni özledim.",
        "Canım sıkılıyor.",
        "Mutluyum.",
    ),
    "soru": (
        "Ne zaman geleceksin?",
        "Saat kaç?",
        "Bugün kim gelecek?",
        "Hava nasıl?",
        "Yarın ne yapacağız?",
    ),
    "sosyal": (
        "Teşekkür ederim.",
        "Evet, lütfen.",
        "Hayır, istemiyorum.",
        "Günaydın.",
        "İyi geceler.",
    ),
}


def write_seed(path: Path) -> int:
    """Çekirdek cümleleri ham veri klasörüne yazar."""
    corpus = Corpus(
        entries=[
            CorpusEntry(text=text, category=category)
            for category, sentences in SEED.items()
            for text in sentences
        ]
    )
    corpus.save(path)
    return len(corpus)


def main() -> None:
    parser = argparse.ArgumentParser(description="AAC derlemini hazırla")
    parser.add_argument("--seed-only", action="store_true", help="Yalnızca çekirdek cümleleri yaz")
    parser.add_argument("--raw", type=Path, default=None, help="Ham derlem (JSONL)")
    parser.add_argument("--min-sentences", type=int, default=0)
    parser.add_argument(
        "--reveal-share",
        type=float,
        default=0.25,
        help="İlk kelimeleri açık yazılmış ek eğitim kaydı oranı (0 kapatır)",
    )
    args = parser.parse_args()

    settings = get_settings()

    if args.seed_only:
        seed_path = args.raw or settings.data_dir / "raw" / "seed_sentences.jsonl"
        count = write_seed(seed_path)
        print(f"{count} çekirdek cümle yazıldı: {seed_path}")
        print(f"Genişletip --raw {seed_path} ile tekrar çalıştırın.")
        return

    raw_path = args.raw or settings.source_corpus_path

    if not raw_path.exists():
        raise SystemExit(
            f"Ham derlem yok: {raw_path}\n"
            "Repodaki data/corpus/aac_sentences.jsonl dosyası eksik ya da --raw yolu yanlış."
        )

    corpus = Corpus.load(raw_path)
    removed = corpus.deduplicate()
    print(f"{len(corpus)} cümle okundu ({removed} tekrar atıldı)")

    for category, count in sorted(corpus.category_counts().items()):
        print(f"  {category:<20} {count:>5}")

    marked = [entry for entry in corpus.entries if entry.note]
    if marked:
        print(f"\n{len(marked)} cümle notlu (ör. 'çıkarılacak'), gözden geçirilmeyi bekliyor")

    if args.min_sentences and len(corpus) < args.min_sentences:
        raise SystemExit(
            f"En az {args.min_sentences} cümle bekleniyordu, {len(corpus)} var. Derlemi genişletin."
        )

    for fixed_split, label in (("test", "test"), ("val", "doğrulama")):
        close = corpus.near_duplicates(fixed_split)
        if not close:
            continue
        print(f"\n{len(close)} cümle {label} kümesindeki bir cümleye çok benziyor:")
        for item in close:
            print(f"  {item.entry.text!r} ~ {item.fixed.text!r}")
        if fixed_split == "test":
            raise SystemExit(
                "Bu cümleler eğitime düşerse test sonucu şişer. Silin ya da test "
                "cümlesinin grubuna bağlayın."
            )

    if settings.study_sentences_path.exists():
        study = StudyMaterials.load(settings.study_sentences_path).all_sentences()
        close = corpus.near_copies_of(study)
        if close:
            print(f"\n{len(close)} cümle kullanıcı testi cümlelerine çok benziyor:")
            for item in close:
                print(f"  {item.entry.text!r} ~ {item.fixed.text!r}")
            raise SystemExit(
                "Model bunları eğitimde görürse kullanıcı testindeki B koşulu ezber "
                "ölçer. Derlemden silin."
            )

    train, val, test = corpus.split()
    corpus.save(settings.corpus_path)
    train.save(settings.train_path)
    val.save(settings.val_path)
    test.save(settings.test_path)
    print(f"\nBölündü: eğitim={len(train)} doğrulama={len(val)} test={len(test)}")
    with_context = [sum(1 for e in part.entries if e.context) for part in (train, val, test)]
    print("  bağlamlı cümle: eğitim={} doğrulama={} test={}".format(*with_context))

    pairs = build_training_pairs(train, reveal_share=args.reveal_share)
    write_pairs(pairs, settings.pairs_path)
    mixed = sum(1 for pair in pairs if pair["revealed"])
    print(f"{len(pairs)} eğitim çifti yazıldı: {settings.pairs_path}")
    print(f"  {mixed} tanesinde ilk kelimeler açık yazılmış (ör. 'su i')")
    print(f"  {sum(1 for pair in pairs if pair['context'])} tanesinin isteminde bağlam var")
    print("\nTest kümesini Ocak'a kadar açmayın.")


if __name__ == "__main__":
    main()
