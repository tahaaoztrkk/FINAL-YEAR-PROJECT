"""AAC cümle derlemi ve eğitim çifti üretimi.

Derlem JSONL biçimindedir: her satır bir kayıt.

    {"text": "Su istiyorum.", "category": "temel_ihtiyac", "group": "su_istemek"}

Kategori alanı, veri dengesini kontrol etmek ve raporda dağılımı göstermek
için gerekli. Bağlam alanı isteğe bağlıdır; bağlamlı/bağlamsız karşılaştırma
bu alanın varlığına dayanır.

Grup alanı aynı anlamı farklı söyleyen cümleleri bağlar ("Su istiyorum." ve
"Susadım."). İkisi de derlemde kalır, çünkü kullanıcılar aynı ihtiyacı farklı
söyler; ama bölmede birlikte hareket ederler. ``note`` alanı gözden geçirilmeyi
bekleyen cümleleri işaretlemek için kullanılır (ör. ``"note": "çıkarılacak"``).
"""

from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from ..nlp.prompts import build_training_record
from ..nlp.schemes import all_schemes, get_scheme, tokenize

CATEGORIES: tuple[str, ...] = (
    "temel_ihtiyac",
    "agri_saglik",
    "pozisyon_bakim",
    "duygu",
    "soru",
    "sosyal",
)

# Simülasyonda kullanıcı en fazla dört kelimeyi açık yazar (beş tur).
MAX_REVEALED_WORDS = 4

# Eğitim kaydı: istem, tamamlama ve denetim için kısaltma bilgileri.
TrainingRecord = dict[str, str | int]


@dataclass
class CorpusEntry:
    """Derlemdeki tek bir cümle."""

    text: str
    category: str = ""
    context: str | None = None
    group: str = ""
    note: str = ""
    # Sabit küme: "train", "val" ya da "test". Boşsa bölme rastgele atar.
    split: str = ""

    @property
    def split_key(self) -> str:
        """Bölmede birlikte kalması gereken cümlelerin ortak anahtarı."""
        return f"group:{self.group}" if self.group else f"text:{self.text.casefold()}"

    def to_json(self) -> str:
        payload: dict[str, str] = {"text": self.text}
        if self.category:
            payload["category"] = self.category
        if self.group:
            payload["group"] = self.group
        if self.context:
            payload["context"] = self.context
        if self.note:
            payload["note"] = self.note
        if self.split:
            payload["split"] = self.split
        return json.dumps(payload, ensure_ascii=False)


SPLITS = ("train", "val", "test")

# İki cümle kelimelerinin bu kadarını paylaşıyorsa ya da harf dizisi bu kadar
# benziyorsa biri ötekinin kopyası sayılır ("Biraz daha uyumak istiyorum." ile
# "Biraz daha yemek istiyorum." gibi). Eşanlamlı ama farklı kelimeli cümleleri
# ("Karnım aç." / "Acıktım.") yakalamaz; onlar için gözden geçirme gerekir.
NEAR_WORD_SHARE = 0.75
NEAR_CHAR_RATIO = 0.9


@dataclass(frozen=True)
class NearDuplicate:
    """Sabit kümedeki bir cümleye fazla benzeyen serbest cümle."""

    entry: CorpusEntry
    fixed: CorpusEntry
    word_share: float
    char_ratio: float


def similarity(a: str, b: str) -> tuple[float, float]:
    """Ortak kelime payı ve harf dizisi benzerliği (ikisi de 0–1)."""
    words_a, words_b = tokenize(a), tokenize(b)
    if not words_a or not words_b:
        return 0.0, 0.0
    shared = len(set(words_a) & set(words_b))
    word_share = shared / max(len(set(words_a)), len(set(words_b)))
    char_ratio = SequenceMatcher(None, " ".join(words_a), " ".join(words_b)).ratio()
    return word_share, char_ratio


def _checked_split(value: object, path: Path, line_number: int) -> str:
    split = str(value or "")
    if split and split not in SPLITS:
        raise ValueError(f"{path}:{line_number} split alanı {SPLITS} olmalı, {split!r} geldi")
    return split


@dataclass
class Corpus:
    """Bellekteki derlem ve üstündeki işlemler."""

    entries: list[CorpusEntry] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> Corpus:
        entries: list[CorpusEntry] = []
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_number} geçerli JSON değil") from exc
                text = record.get("text")
                if not isinstance(text, str) or not text.strip():
                    continue
                entries.append(
                    CorpusEntry(
                        text=text.strip(),
                        category=str(record.get("category", "")),
                        context=record.get("context"),
                        group=str(record.get("group", "")),
                        note=str(record.get("note", "")),
                        split=_checked_split(record.get("split", ""), path, line_number),
                    )
                )
        return cls(entries=entries)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for entry in self.entries:
                handle.write(entry.to_json() + "\n")

    def deduplicate(self) -> int:
        """Birebir aynı cümleleri atar. Kaç tane atıldığını döner.

        Üretilen veride tekrar kaçınılmaz; test kümesine eğitimden cümle
        sızmasının en sık yolu budur.
        """
        seen: set[str] = set()
        unique: list[CorpusEntry] = []
        for entry in self.entries:
            key = entry.text.strip().casefold()
            if key in seen:
                continue
            seen.add(key)
            unique.append(entry)
        removed = len(self.entries) - len(unique)
        self.entries = unique
        return removed

    def category_counts(self) -> Counter[str]:
        return Counter(entry.category or "belirtilmemis" for entry in self.entries)

    def split(
        self, train: float = 0.8, val: float = 0.1, seed: int = 42
    ) -> tuple[Corpus, Corpus, Corpus]:
        """Eğitim / doğrulama / test olarak böler.

        Bölme anlam grubu düzeyinde yapılır: "Su istiyorum." eğitime,
        "Susadım." doğrulamaya düşerse model ezberden kazanmış gibi görünür.
        Grubu olmayan cümle kendi başına bir gruptur. Tohum sabittir: aynı
        bölme her koşuda aynı çıkar, yoksa koşular arası karşılaştırma
        anlamsızlaşır.

        ``split`` alanı dolu cümleler (ve gruptaşları) o kümede kalır. Test
        kümesi sabitlenmişse yeni cümleler yalnızca eğitim ve doğrulamaya
        dağıtılır.
        """
        if not 0 < train < 1 or not 0 <= val < 1 or train + val >= 1:
            raise ValueError("Oranlar 0–1 arasında olmalı ve toplamı 1'den küçük kalmalı")

        groups: dict[str, list[CorpusEntry]] = {}
        for entry in self.entries:
            groups.setdefault(entry.split_key, []).append(entry)

        parts: tuple[list[CorpusEntry], list[CorpusEntry], list[CorpusEntry]] = ([], [], [])
        index = {"train": 0, "val": 1, "test": 2}
        free: list[list[CorpusEntry]] = []
        for key, members in groups.items():
            fixed = {m.split for m in members if m.split}
            if len(fixed) > 1:
                raise ValueError(f"{key} grubundaki cümleler farklı kümelere sabitlenmiş: {fixed}")
            if fixed:
                parts[index[fixed.pop()]].extend(members)
            else:
                free.append(members)
        random.Random(seed).shuffle(free)

        # Test kümesi sabitlenmişse yeni cümleler teste girmez: elle yazılmış
        # test cümleleri derlem büyüse de aynı kalır, sonuçlar karşılaştırılabilir.
        if parts[2]:
            n_open = len(self.entries) - len(parts[2])
            train_target = int(n_open * train / (train + val))
            val_target = n_open
        else:
            n = len(self.entries)
            train_target = int(n * train)
            val_target = int(n * val)
        for members in free:
            if len(parts[0]) < train_target:
                parts[0].extend(members)
            elif len(parts[1]) < val_target:
                parts[1].extend(members)
            else:
                parts[2].extend(members)
        return Corpus(parts[0]), Corpus(parts[1]), Corpus(parts[2])

    def near_duplicates(self, fixed_split: str = "test") -> list[NearDuplicate]:
        """``fixed_split`` kümesine sabitli cümlelere fazla benzeyen serbest cümleler.

        Eğitime düşen bir kopya, test cümlesini ezberden bilinir kılar. Aynı
        gruptakiler zaten birlikte o kümeye gider, onlara bakılmaz.
        """
        return self._close_to([entry for entry in self.entries if entry.split == fixed_split])

    def near_copies_of(self, texts: list[str]) -> list[NearDuplicate]:
        """Eğitime girebilecek ve derlem dışı cümlelere (ör. kullanıcı testi) benzeyenler.

        Doğrulama ve test kümesine sabitli cümleler eğitimde görülmez, onlara bakılmaz.
        """
        targets = [CorpusEntry(text=text) for text in texts]
        return self._close_to(targets, skip=("val", "test"))

    def _close_to(
        self, targets: list[CorpusEntry], skip: tuple[str, ...] = SPLITS
    ) -> list[NearDuplicate]:
        found: list[NearDuplicate] = []
        for entry in self.entries:
            if entry.split in skip:
                continue
            for target in targets:
                if entry.group and entry.group == target.group:
                    continue
                word_share, char_ratio = similarity(entry.text, target.text)
                if word_share >= NEAR_WORD_SHARE or char_ratio >= NEAR_CHAR_RATIO:
                    found.append(NearDuplicate(entry, target, word_share, char_ratio))
        return found

    def __len__(self) -> int:
        return len(self.entries)


def build_training_pairs(
    corpus: Corpus,
    schemes: list[str] | None = None,
    reveal_share: float = 0.25,
    seed: int = 42,
) -> list[TrainingRecord]:
    """Derlemden ince ayar kayıtları üretir.

    Her cümle her şema için bir kayıt doğurur: 3.000 cümle x 4 şema = 12.000
    örnek. Şema etiketi istemin içinde olduğu için tek model dört şemayı da
    öğrenir; bu, karşılaştırmayı aynı ağırlıklar üstünde yaptığı için ayrı
    model eğitmekten hem ucuz hem adildir.

    Kayıtların ``reveal_share`` kadarına bir kayıt daha eklenir: ilk birkaç
    kelimesi açık yazılmış kısaltma ("su i"). Doğru cümle listede çıkmayınca
    kullanıcı böyle devam eder ve simülasyon bunu ölçer; model bu biçimi
    eğitimde hiç görmezse sonraki turlarda ne yapacağını bilemez.
    ``revealed`` alanı açık yazılan kelime sayısıdır, saf kısaltmada 0'dır.
    """
    if not 0.0 <= reveal_share <= 1.0:
        raise ValueError("reveal_share 0 ile 1 arasında olmalı")

    scheme_ids = schemes or [s.id for s in all_schemes()]
    rng = random.Random(seed)
    records: list[TrainingRecord] = []

    for entry in corpus.entries:
        word_count = len(tokenize(entry.text))
        for scheme_id in scheme_ids:
            handler = get_scheme(scheme_id)
            abbreviation = handler.abbreviate(entry.text)
            if not abbreviation.strip():
                continue
            records.append(_training_record(entry, scheme_id, abbreviation, revealed=0))

            if word_count > 1 and rng.random() < reveal_share:
                revealed = rng.randint(1, min(word_count - 1, MAX_REVEALED_WORDS))
                mixed = handler.abbreviate_revealing(entry.text, revealed)
                records.append(_training_record(entry, scheme_id, mixed, revealed=revealed))

    return records


def _training_record(
    entry: CorpusEntry, scheme_id: str, abbreviation: str, revealed: int
) -> TrainingRecord:
    record: TrainingRecord = {
        **build_training_record(abbreviation, entry.text, scheme_id, context=entry.context)
    }
    record["scheme"] = scheme_id
    record["abbreviation"] = abbreviation
    record["sentence"] = entry.text
    record["revealed"] = revealed
    return record


def write_pairs(records: list[TrainingRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
