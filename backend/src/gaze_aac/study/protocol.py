"""Kullanıcı testinin planı.

Etik kurul belgesindeki tasarımın kodu: denek içi, iki koşul (A harf harf,
B kısaltma ve aday listesi), katılımcıların yarısı B ile başlar. Her koşul
kendi alıştırma cümleleriyle açılır, ardından ölçülen set gelir.

Sıra katılımcı kodundan çıkar (tek numara AB, çift numara BA). Deneyi
yürüten kişinin seçmesine bırakılmaz: elle verilen sıra yorgun bir günde
kayar ve sonradan fark edilmez.

Cümle setleri blok sırasına bağlıdır: ilk blok hep 1. seti, ikinci blok hep
2. seti alır. Böylece her koşul katılımcıların yarısında bir seti, yarısında
diğerini görür ve setler arasındaki zorluk farkı koşul farkına karışmaz.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from ..nlp.schemes import get_scheme, tokenize
from ..schemas.study import Condition, StudyBlock, StudyTrial

# Kod klasör adı olur; harf + rakam dışında bir şeye izin verilmez.
_PARTICIPANT_RE = re.compile(r"^[A-Z][0-9]{1,3}$")


def normalize_participant_id(raw: str) -> str:
    """Katılımcı kodunu tek biçime getirir: ``k7`` -> ``K07``.

    Raises:
        ValueError: Kod harf + rakam biçiminde değilse.
    """
    code = raw.strip().upper()
    if not _PARTICIPANT_RE.match(code):
        raise ValueError(f"Katılımcı kodu K07 biçiminde olmalı, gelen: {raw!r}")
    return f"{code[0]}{int(code[1:]):02d}"


def condition_order(participant_id: str) -> tuple[Condition, Condition]:
    """Koşul sırası: tek numaralı katılımcı A ile, çift numaralı B ile başlar."""
    number = int(normalize_participant_id(participant_id)[1:])
    return ("A", "B") if number % 2 == 1 else ("B", "A")


def normalize_sentence(text: str) -> str:
    """Karşılaştırma biçimi: Türkçe küçük harf, noktalama yok, tek boşluk.

    Arayüzdeki ``normalizeSentence`` ile aynı kural; ikisi ayrışırsa doğru
    yazılan cümle yanlış sayılır.
    """
    return " ".join(tokenize(text))


def sentences_match(output: str, target: str) -> bool:
    """Katılımcının ürettiği metin hedef cümle mi."""
    normalized = normalize_sentence(output)
    return bool(normalized) and normalized == normalize_sentence(target)


@dataclass(frozen=True)
class StudyMaterials:
    """``data/study/sentences.json`` içeriği."""

    scheme: str
    practice: dict[Condition, tuple[str, ...]]
    sets: tuple[tuple[str, ...], tuple[str, ...]]
    digest: str

    @classmethod
    def load(cls, path: Path) -> StudyMaterials:
        """Dosyayı okur ve tasarımı bozacak hataları baştan yakalar.

        Raises:
            FileNotFoundError: Dosya yoksa.
            ValueError: Biçim ya da tasarım hatası varsa.
        """
        raw = path.read_bytes()
        data = json.loads(raw)

        scheme = str(data.get("scheme", "S1")).upper()
        try:
            get_scheme(scheme)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc

        practice_raw = data.get("practice", {})
        practice: dict[Condition, tuple[str, ...]] = {
            "A": tuple(practice_raw.get("A", ())),
            "B": tuple(practice_raw.get("B", ())),
        }

        sets_raw = data.get("sets", [])
        if len(sets_raw) != 2:
            raise ValueError(f"İki cümle seti gerekiyor, {len(sets_raw)} tane var")
        first, second = (tuple(sentences) for sentences in sets_raw)
        if not first or len(first) != len(second):
            raise ValueError(
                f"Setler boş olmamalı ve eşit uzunlukta olmalı: {len(first)} / {len(second)}"
            )

        materials = cls(
            scheme=scheme,
            practice=practice,
            sets=(first, second),
            digest=hashlib.sha256(raw).hexdigest()[:12],
        )

        seen: set[str] = set()
        for sentence in materials.all_sentences():
            normalized = normalize_sentence(sentence)
            if not normalized:
                raise ValueError(f"Boş cümle: {sentence!r}")
            if normalized in seen:
                raise ValueError(f"Aynı cümle iki kez geçiyor: {sentence!r}")
            seen.add(normalized)
        return materials

    def all_sentences(self) -> list[str]:
        return [*self.practice["A"], *self.practice["B"], *self.sets[0], *self.sets[1]]


def build_plan(participant_id: str, materials: StudyMaterials) -> list[StudyBlock]:
    """Katılımcının iki bloğu, sırasıyla."""
    blocks: list[StudyBlock] = []
    for position, condition in enumerate(condition_order(participant_id)):
        texts = [(text, True) for text in materials.practice[condition]]
        texts += [(text, False) for text in materials.sets[position]]
        blocks.append(
            StudyBlock(
                condition=condition,
                scheme=materials.scheme,
                trials=[
                    StudyTrial(index=index, text=text, practice=practice)
                    for index, (text, practice) in enumerate(texts)
                ],
            )
        )
    return blocks
