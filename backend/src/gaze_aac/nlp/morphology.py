"""S4 şeması için Zemberek ile ek sınıfı çözümlemesi.

S4'te kullanıcı her kelimenin baş harfinden sonra ekin ne olduğunu seçer
("istemiyorum" -> ``i-NEG+PROG+1S``). Bu etiketler iki yerde hesaplanır:
eğitim çiftleri üretilirken ve modelin adayları geri kontrol edilirken. İkisi
de buradan geçer, böylece model hangi etiketle eğitildiyse onunla ölçülür.

Eski kural tablosu (``schemes.guess_suffix_tag``) yalnızca kelime sonuna
bakıyordu: "masa" sonundaki "a" yüzünden ``DAT``, "telefonumu" ise hiçbir şey
alıyordu. Zemberek kelimeyi köküne ve eklerine ayırır, cümle bağlamında
belirsizliği giderir ("yüzü" isim mi, fiil mi). Zemberek'in tanımadığı
kelimelerde (özel ad, yazım hatası) kural tablosuna dönülür.

Zemberek'in Python sürümü (``zemberek-python``) bakımsız iki eski bağımlılığa
dayanır; ``_install_shims`` ikisini de kurulum gerektirmeden giderir.
"""

from __future__ import annotations

import logging
import sys
import types
import typing
from functools import lru_cache
from pathlib import Path
from typing import Any

# Zemberek biçimbirimi -> S4 etiketi. Birden çok biçimbirim aynı etikete
# düşebilir; bir kelimede aynı etiket bir kez yazılır.
#
# Kişi ekleri hem fiilde (``A1sg``: geliyor-um) hem isimde (``P1sg``:
# anne-m) "ben" anlamı taşır; kullanıcı ikisini de "ben" diye düşünür.
# Çoğul kişi ve iyelik (gidelim, evimiz) ayrı etiket olmadığı için ``PLUR``
# sayılır. Yeterlilik olumsuzu ("gel-eme-yeceğim") ``NEG``'dir.
#
# Yalnızca kelimede görünen ekler etiket alır. Zemberek "sür" emrine ve
# "ben" zamirine de 2. ve 1. tekil kişi yazar, ama ortada ek yoktur;
# kullanıcı yalın kelimeye etiket eklemeyi düşünmez.
MORPHEME_TAGS: dict[str, str] = {
    "Neg": "NEG",
    "Unable": "NEG",
    "Past": "PAST",
    "Narr": "PAST",
    "Fut": "FUT",
    "Prog1": "PROG",
    "Prog2": "PROG",
    "Ques": "Q",
    "A1sg": "1S",
    "P1sg": "1S",
    "A2sg": "2S",
    "P2sg": "2S",
    "A1pl": "PLUR",
    "A2pl": "PLUR",
    "A3pl": "PLUR",
    "P1pl": "PLUR",
    "P2pl": "PLUR",
    "P3pl": "PLUR",
    "Dat": "DAT",
    "Loc": "LOC",
    "Abl": "ABL",
    "Acc": "ACC",
}


def tags_from_morphemes(morphemes: list[str], allowed: typing.Collection[str]) -> str:
    """Biçimbirim kimliklerini sıralı, tekrarsız S4 etiketine çevirir.

    ``allowed`` dışındaki etiketler atılır: arayüzde olmayan bir etiketi
    kullanıcı giremez, kısaltmada da yer almamalı.

    >>> tags_from_morphemes(["Verb", "Neg", "Prog1", "A1sg"], {"NEG", "PROG", "1S"})
    'NEG+PROG+1S'
    """
    tags: list[str] = []
    for morpheme in morphemes:
        tag = MORPHEME_TAGS.get(morpheme)
        if tag and tag in allowed and tag not in tags:
            tags.append(tag)
    return "+".join(tags)


def _install_shims() -> None:
    """``zemberek-python``ın eski bağımlılıklarını yerine koyar.

    - ``antlr4-python3-runtime`` 4.8, Python 3.13'te kaldırılan ``typing.io``
      modülünü içe aktarır (yalnızca tür ipucu için).
    - Zemberek kaynak dosyalarını ``pkg_resources`` ile bulur; setuptools 81
      bu modülü kaldırdı.

    İkisi de yalnızca eksikse eklenir; gerçek modül varsa ona dokunulmaz.
    """
    if "typing.io" not in sys.modules:
        try:
            __import__("typing.io")
        except ImportError:
            shim = types.ModuleType("typing.io")
            shim.TextIO = typing.TextIO  # type: ignore[attr-defined]
            sys.modules["typing.io"] = shim

    try:
        import pkg_resources  # noqa: F401
    except ImportError:

        def resource_filename(package: str, resource: str) -> str:
            module = __import__(package)
            return str(Path(module.__file__ or "").parent / resource)

        shim = types.ModuleType("pkg_resources")
        shim.resource_filename = resource_filename  # type: ignore[attr-defined]
        sys.modules["pkg_resources"] = shim


class ZemberekTagger:
    """Zemberek ile kelime ve cümle düzeyinde ek sınıfı etiketleyici.

    Zemberek ilk kullanımda yüklenir (birkaç saniye). Sonuçlar önbelleğe
    alınır: geri kontrol aynı cümleleri tekrar tekrar sorar.
    """

    def __init__(self, allowed: typing.Collection[str], fallback: Any = None) -> None:
        """
        Args:
            allowed: Üretilebilecek etiketler (``schemes.SUFFIX_TAGS``).
            fallback: Zemberek'in tanımadığı kelime için ``word -> str``.
        """
        self.allowed = frozenset(allowed)
        self._fallback = fallback
        self._morphology: Any = None

    def _load(self) -> Any:
        if self._morphology is None:
            _install_shims()
            # Zemberek yüklenirken uyarı ve bilgi satırları basar.
            logging.getLogger("zemberek").setLevel(logging.ERROR)
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from zemberek import TurkishMorphology

                self._morphology = TurkishMorphology.create_with_defaults()
        return self._morphology

    def warm_up(self) -> None:
        """Zemberek'i şimdi yükler; ilk isteğin gecikmesine eklenmesin."""
        self._load()

    def _tag_analysis(self, word: str, analysis: Any) -> str:
        if analysis is None or analysis.is_unknown():
            return self._fallback(word) if self._fallback is not None else ""
        # İlk öğe kökün kendisidir (Noun, Verb...), hiçbir etikete düşmez.
        morphemes = [data.morpheme.id_ for data in analysis.morpheme_data_list if data.surface]
        return tags_from_morphemes(morphemes, self.allowed)

    def tag(self, word: str) -> str:
        """Tek kelimenin etiketi, bağlamsız."""
        return self.tag_sentence((word,))[0]

    def tag_sentence(self, words: typing.Sequence[str]) -> list[str]:
        """Kelime listesinin etiketleri, cümle bağlamında belirsizlik giderilerek.

        Kelimeler ``schemes.tokenize`` çıktısıdır (küçük harf, noktalamasız).
        Zemberek'in kendi bölütleyicisi farklı sayıda parça çıkarırsa her
        kelime tek başına çözümlenir.
        """
        return list(self._tag_tuple(tuple(words)))

    def _best(self, text: str) -> list[Any]:
        """Metnin cümle bağlamında en iyi çözümlemeleri.

        Özel ad ve kısaltma okumaları, başka okuma varsa elenir: kelimeler
        küçük harfle gelir ve AAC cümlelerinde "selam" neredeyse hiç "Sela"
        adının iyelikli hali, "uyu" da "U" kısaltmasının belirtme hali değildir.
        Zemberek'in bağlam modeli bunları bazen seçiyor.
        """
        morphology = self._load()  # önce yüklenmeli: uyumluluk yamaları burada kurulur
        from zemberek.morphology.analysis.word_analysis import WordAnalysis

        filtered = []
        for word_analysis in morphology.analyze_sentence(text):
            results = word_analysis.analysis_results
            common = tuple(a for a in results if not _is_name_or_abbreviation(a))
            if common and len(common) < len(results):
                word_analysis = WordAnalysis(
                    word_analysis.inp, common, word_analysis.normalized_input
                )
            filtered.append(word_analysis)
        return list(morphology.disambiguate(text, filtered).best_analysis())

    @lru_cache(maxsize=65536)  # noqa: B019 - etiketleyici süreç boyunca yaşar
    def _tag_tuple(self, words: tuple[str, ...]) -> tuple[str, ...]:
        if not words:
            return ()
        best = self._best(" ".join(words))
        if len(best) == len(words):
            return tuple(self._tag_analysis(w, a) for w, a in zip(words, best, strict=True))
        tags: list[str] = []
        for word in words:
            single = self._best(word)
            tags.append(self._tag_analysis(word, single[0] if len(single) == 1 else None))
        return tuple(tags)


def _is_name_or_abbreviation(analysis: Any) -> bool:
    secondary = getattr(analysis.item, "secondary_pos", None)
    return getattr(secondary, "short_form", "") in {"Prop", "Abbrv"}
