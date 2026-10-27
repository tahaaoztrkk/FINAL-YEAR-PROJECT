"""AAC cümle derlemi ve eğitim çifti üretimi.

Derlem JSONL biçimindedir: her satır bir kayıt.

    {"text": "Su istiyorum.", "category": "temel_ihtiyac", "group": "su_istemek"}

Kategori alanı, veri dengesini kontrol etmek ve raporda dağılımı göstermek
için gerekli. Bağlam alanı isteğe bağlıdır; bağlamlı/bağlamsız karşılaştırma
bu alanın varlığına dayanır.

Grup alanı aynı anlamı farklı söyleyen cümleleri bağlar ("Su istiyorum." ve
"Susadım."). İkisi de derlemde kalır, çünkü kullanıcılar aynı ihtiyacı farklı
söyler; ama bölmede birlikte hareket ederler. Grubun ilki dışındakiler
``"note": "çıkarılacak"`` ile işaretlidir: ekip gözden geçirince silinecekler.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..nlp.prompts import build_training_record
from ..nlp.schemes import all_schemes, get_scheme

CATEGORIES: tuple[str, ...] = (
    "temel_ihtiyac",
    "agri_saglik",
    "pozisyon_bakim",
    "duygu",
    "soru",
    "sosyal",
)


@dataclass
class CorpusEntry:
    """Derlemdeki tek bir cümle."""

    text: str
    category: str = ""
    context: str | None = None
    group: str = ""
    note: str = ""

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
        return json.dumps(payload, ensure_ascii=False)


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
        """
        if not 0 < train < 1 or not 0 <= val < 1 or train + val >= 1:
            raise ValueError("Oranlar 0–1 arasında olmalı ve toplamı 1'den küçük kalmalı")

        groups: dict[str, list[CorpusEntry]] = {}
        for entry in self.entries:
            groups.setdefault(entry.split_key, []).append(entry)
        ordered = list(groups.values())
        random.Random(seed).shuffle(ordered)

        n = len(self.entries)
        train_target = int(n * train)
        val_target = int(n * val)
        parts: tuple[list[CorpusEntry], list[CorpusEntry], list[CorpusEntry]] = ([], [], [])
        for members in ordered:
            if len(parts[0]) < train_target:
                parts[0].extend(members)
            elif len(parts[1]) < val_target:
                parts[1].extend(members)
            else:
                parts[2].extend(members)
        return Corpus(parts[0]), Corpus(parts[1]), Corpus(parts[2])

    def __len__(self) -> int:
        return len(self.entries)


def build_training_pairs(corpus: Corpus, schemes: list[str] | None = None) -> list[dict[str, str]]:
    """Derlemden ince ayar kayıtları üretir.

    Her cümle her şema için bir kayıt doğurur: 3.000 cümle x 4 şema = 12.000
    örnek. Şema etiketi istemin içinde olduğu için tek model dört şemayı da
    öğrenir; bu, karşılaştırmayı aynı ağırlıklar üstünde yaptığı için ayrı
    model eğitmekten hem ucuz hem adildir.
    """
    scheme_ids = schemes or [s.id for s in all_schemes()]
    records: list[dict[str, str]] = []

    for entry in corpus.entries:
        for scheme_id in scheme_ids:
            handler = get_scheme(scheme_id)
            abbreviation = handler.abbreviate(entry.text)
            if not abbreviation.strip():
                continue
            record = build_training_record(
                abbreviation, entry.text, scheme_id, context=entry.context
            )
            record["scheme"] = scheme_id
            record["abbreviation"] = abbreviation
            record["sentence"] = entry.text
            records.append(record)

    return records


def write_pairs(records: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
