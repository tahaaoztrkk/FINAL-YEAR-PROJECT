"""Türkçe kısaltma şemaları.

Projenin araştırma sorusu burada somutlaşıyor: İngilizcede kelimenin baş harfi
yeterli bilgi taşır, Türkçede taşımaz. "gelemeyeceğim" kelimesinin baş harfi
yalnızca kökü verir; olumsuzluk, yeterlilik ve gelecek zaman eki kaybolur.

Dört şema bu kaybı farklı noktalarda telafi eder. Hepsi aynı arayüzü uygular,
böylece simülasyon tek döngüyle dördünü de ölçebilir:

    S1  baş harf                     "y h g i"
    S2  ilk iki harf                 "ya ha gi is"
    S3  ilk + son harf               "yn he gk im"
    S4  baş harf + ek sınıfı etiketi "y h-E g-MEK i-NEG1S"

Yeni şema eklemek için ``AbbreviationScheme`` türetin ve ``register`` ile
kaydedin; simülasyon ve API otomatik olarak görür.
"""

from __future__ import annotations

import re
import unicodedata
from abc import ABC, abstractmethod

# Türkçe'ye özgü küçültme: I -> ı, İ -> i. str.lower() bunu yanlış yapar.
_UPPER_TR = "ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZQWX"
_LOWER_TR = "abcçdefgğhıijklmnoöprsştuüvyzqwx"
_LOWER_MAP = str.maketrans(_UPPER_TR, _LOWER_TR)

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def turkish_lower(text: str) -> str:
    """Türkçe kurallarına göre küçük harfe çevirir."""
    return text.translate(_LOWER_MAP).lower()


def turkish_capitalize(text: str) -> str:
    """İlk harfi Türkçe kurallarına göre büyütür: i -> İ, ı -> I.

    ``str.capitalize`` hem "istiyorum"u "Istiyorum" yapar hem de kalan
    harfleri küçültür.
    """
    if not text:
        return text
    first = {"i": "İ", "ı": "I"}.get(text[0], text[0].upper())
    return first + text[1:]


def tokenize(sentence: str) -> list[str]:
    """Cümleyi kelimelere ayırır; noktalama ve rakamlar atılır."""
    normalized = unicodedata.normalize("NFC", sentence)
    return [turkish_lower(w) for w in _WORD_RE.findall(normalized)]


class AbbreviationScheme(ABC):
    """Bir cümleyi kısaltmaya çeviren kural kümesi."""

    id: str = ""
    name: str = ""
    description: str = ""

    @abstractmethod
    def abbreviate_word(self, word: str) -> str:
        """Tek kelimenin kısaltması."""

    def abbreviate(self, sentence: str) -> str:
        """Cümlenin tamamının kısaltması, kelimeler boşlukla ayrılmış."""
        return " ".join(self.abbreviate_word(w) for w in tokenize(sentence))

    def matches(self, sentence: str, abbreviation: str) -> bool:
        """Verilen cümle bu kısaltmaya uyuyor mu.

        Aday üretiminden sonraki geri kontrol adımı budur: model Türkçede
        kolayca "yakın ama yanlış" cümle üretir, bu filtre onları eler.

        İki taraf da normalleştirilir. S4'ün ek etiketleri büyük harfle
        üretilir ama kullanıcıdan küçük harfle gelebilir; tek tarafı
        normalleştirmek her S4 adayını sessizce geçersiz sayar.
        """
        return normalize_abbreviation(self.abbreviate(sentence)) == normalize_abbreviation(
            abbreviation
        )

    def keystrokes(self, sentence: str) -> int:
        """Kısaltmayı girmek için gereken seçim sayısı.

        Boşluklar sayılmaz: arayüzde kelime sınırı ayrı bir tuş değil, aday
        listesine geçişle örtülü olarak verilir.
        """
        return len(self.abbreviate(sentence).replace(" ", ""))


def normalize_abbreviation(abbreviation: str) -> str:
    """Kısaltmayı karşılaştırmaya hazır hale getirir."""
    return " ".join(turkish_lower(abbreviation).split())


class InitialScheme(AbbreviationScheme):
    """S1 — her kelimenin yalnızca ilk harfi.

    En yüksek tuş tasarrufu, en yüksek belirsizlik. Taban çizgisi budur;
    İngilizce literatürdeki şema da bu.
    """

    id = "S1"
    name = "Baş harf"
    description = "Her kelimenin ilk harfi"

    def abbreviate_word(self, word: str) -> str:
        return word[:1]


class TwoLetterScheme(AbbreviationScheme):
    """S2 — her kelimenin ilk iki harfi.

    Kökü ayırt etmeye yardım eder ("gel-" ile "git-" artık karışmaz) ama ek
    bilgisi yine kaybolur.
    """

    id = "S2"
    name = "İlk iki harf"
    description = "Her kelimenin ilk iki harfi"

    def abbreviate_word(self, word: str) -> str:
        return word[:2]


class FirstLastScheme(AbbreviationScheme):
    """S3 — ilk ve son harf.

    Son harf, ekin bir kısmını dolaylı olarak taşır: "gideceğim" -> "gm",
    "gitti" -> "gi". Tuş sayısı S2 ile aynı, bilgi dağılımı farklı.
    """

    id = "S3"
    name = "Baş + son harf"
    description = "Kelimenin ilk ve son harfi"

    def abbreviate_word(self, word: str) -> str:
        if len(word) == 1:
            return word
        return word[0] + word[-1]


# Ek sınıfı etiketleri. Arayüzde her biri ayrı bir büyük hedef olur.
# Liste bilinçli olarak kısa tutuldu: 12 hedefli ızgaraya sığması gerekiyor.
SUFFIX_TAGS: dict[str, str] = {
    "NEG": "olumsuz",
    "PAST": "geçmiş zaman",
    "FUT": "gelecek zaman",
    "PROG": "şimdiki zaman",
    "Q": "soru",
    "1S": "1. tekil kişi",
    "2S": "2. tekil kişi",
    "PLUR": "çoğul",
    "DAT": "yönelme (-e)",
    "LOC": "bulunma (-de)",
    "ABL": "ayrılma (-den)",
    "ACC": "belirtme (-i)",
}

# Kural tabanlı yaklaşık çözümleme. Morfolojik olarak doğru analiz için
# Zemberek kullanılır (morphology.py); bu tablo Zemberek yokken de şemanın
# çalışmasını ve testlerin hızlı kalmasını sağlar.
_SUFFIX_RULES: tuple[tuple[str, str], ...] = (
    ("miyorum", "NEG+PROG+1S"),
    ("miyor", "NEG+PROG"),
    ("muyorum", "NEG+PROG+1S"),
    ("müyorum", "NEG+PROG+1S"),
    ("mıyorum", "NEG+PROG+1S"),
    ("mıyor", "NEG+PROG"),
    ("meyeceğim", "NEG+FUT+1S"),
    ("mayacağım", "NEG+FUT+1S"),
    ("eceğim", "FUT+1S"),
    ("acağım", "FUT+1S"),
    ("yorum", "PROG+1S"),
    ("iyorum", "PROG+1S"),
    ("ıyorum", "PROG+1S"),
    ("uyorum", "PROG+1S"),
    ("üyorum", "PROG+1S"),
    ("yor", "PROG"),
    ("dım", "PAST+1S"),
    ("dim", "PAST+1S"),
    ("dum", "PAST+1S"),
    ("düm", "PAST+1S"),
    ("tım", "PAST+1S"),
    ("tim", "PAST+1S"),
    ("di", "PAST"),
    ("dı", "PAST"),
    ("ti", "PAST"),
    ("tı", "PAST"),
    ("ler", "PLUR"),
    ("lar", "PLUR"),
    ("den", "ABL"),
    ("dan", "ABL"),
    ("ten", "ABL"),
    ("tan", "ABL"),
    ("de", "LOC"),
    ("da", "LOC"),
    ("te", "LOC"),
    ("ta", "LOC"),
    ("ye", "DAT"),
    ("ya", "DAT"),
    ("e", "DAT"),
    ("a", "DAT"),
    ("yi", "ACC"),
    ("yı", "ACC"),
    ("i", "ACC"),
    ("ı", "ACC"),
)


def guess_suffix_tag(word: str) -> str:
    """Kelimenin ek sınıfını kaba kuralla tahmin eder.

    Returns:
        ``NEG+PROG+1S`` gibi birleşik etiket, ek yoksa boş dize.
    """
    for ending, tag in _SUFFIX_RULES:
        if len(word) > len(ending) and word.endswith(ending):
            return tag
    return ""


class SuffixTaggedScheme(AbbreviationScheme):
    """S4 — baş harf + ek sınıfı etiketi.

    En bilgili şema: kullanıcı baş harfi girer, sonra ekin ne olduğunu tek
    seçimle söyler. Tuş tasarrufu S1'den düşük ama belirsizlik çok daha az.

    Hipotez: Türkçede S4, S1'den daha az tasarruf etmesine rağmen toplam
    seçim sayısını düşürür, çünkü yanlış adayı düzeltme turlarını ortadan
    kaldırır.
    """

    id = "S4"
    name = "Ek işaretli baş harf"
    description = "Baş harf ve ek sınıfı etiketi"

    def __init__(self, tagger: object | None = None) -> None:
        """
        Args:
            tagger: ``tag(word) -> str`` arayüzü olan çözümleyici. Verilmezse
                kural tabanlı tahmin kullanılır.
        """
        self._tagger = tagger

    def _tag(self, word: str) -> str:
        if self._tagger is not None and hasattr(self._tagger, "tag"):
            return str(self._tagger.tag(word))  # type: ignore[attr-defined]
        return guess_suffix_tag(word)

    def abbreviate_word(self, word: str) -> str:
        tag = self._tag(word)
        return f"{word[:1]}-{tag}" if tag else word[:1]

    def keystrokes(self, sentence: str) -> int:
        """Etiket tek seçimle girilir, harf harf değil.

        Bu yüzden S4'ün maliyeti, kısaltma dizesinin karakter sayısı değil:
        kelime başına 1 harf + (varsa) etiket sayısı kadar seçimdir.
        """
        total = 0
        for word in tokenize(sentence):
            total += 1
            tag = self._tag(word)
            if tag:
                total += len(tag.split("+"))
        return total


_REGISTRY: dict[str, AbbreviationScheme] = {}


def register(scheme: AbbreviationScheme) -> AbbreviationScheme:
    """Şemayı kayıt defterine ekler."""
    _REGISTRY[scheme.id] = scheme
    return scheme


def get_scheme(scheme_id: str) -> AbbreviationScheme:
    """Kimliğe göre şema döner.

    Raises:
        KeyError: Bilinmeyen şema kimliği.
    """
    try:
        return _REGISTRY[scheme_id.upper()]
    except KeyError as exc:
        known = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"Bilinmeyen şema: {scheme_id!r}. Tanımlı olanlar: {known}") from exc


def all_schemes() -> list[AbbreviationScheme]:
    """Kayıtlı tüm şemalar, kimlik sırasına göre."""
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


register(InitialScheme())
register(TwoLetterScheme())
register(FirstLastScheme())
register(SuffixTaggedScheme())
