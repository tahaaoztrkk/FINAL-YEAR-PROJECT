"""Türkçe kısaltma şemaları.

Projenin araştırma sorusu burada somutlaşıyor: İngilizcede kelimenin baş harfi
yeterli bilgi taşır, Türkçede taşımaz. "gelemeyeceğim" kelimesinin baş harfi
yalnızca kökü verir; olumsuzluk, yeterlilik ve gelecek zaman eki kaybolur.

Dört şema bu kaybı farklı noktalarda telafi eder. Hepsi aynı arayüzü uygular,
böylece simülasyon tek döngüyle dördünü de ölçebilir:

    S1  baş harf                     "y h g i"
    S2  ilk iki harf                 "ya ha gi is"
    S3  ilk + son harf               "yn he gk im"
    S4  baş harf + ek sınıfı etiketi "y h g i-NEG+PROG+1S"

Yeni şema eklemek için ``AbbreviationScheme`` türetin ve ``register`` ile
kaydedin; simülasyon ve API otomatik olarak görür.
"""

from __future__ import annotations

import re
import unicodedata
from abc import ABC, abstractmethod
from collections.abc import Sequence

from .morphology import ZemberekTagger

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

    def abbreviate_words(self, words: Sequence[str]) -> list[str]:
        """Kelime listesinin kısaltmaları.

        Varsayılan olarak her kelime tek başına kısaltılır. Kısaltması cümle
        bağlamına bağlı olan şemalar (S4) bunu ezer; cümle düzeyindeki bütün
        işlemler buradan geçer, böylece eğitim çifti ile geri kontrol aynı
        kısaltmayı görür.
        """
        return [self.abbreviate_word(w) for w in words]

    def abbreviate(self, sentence: str) -> str:
        """Cümlenin tamamının kısaltması, kelimeler boşlukla ayrılmış."""
        return " ".join(self.abbreviate_words(tokenize(sentence)))

    def abbreviate_revealing(self, sentence: str, revealed: int) -> str:
        """İlk ``revealed`` kelimesi açık yazılmış kısaltma: ``"su i"``.

        Doğru cümle listede çıkmayınca kullanıcı baştan birer kelime açık
        yazar. Simülasyonun sonraki turları ve eğitim verisi bu biçimi aynı
        yerden alır, yoksa model hiç görmediği bir girdiyle ölçülür.
        """
        words = tokenize(sentence)
        abbreviations = self.abbreviate_words(words)
        return " ".join(
            word if index < revealed else abbreviation
            for index, (word, abbreviation) in enumerate(zip(words, abbreviations, strict=True))
        )

    def matches(self, sentence: str, abbreviation: str) -> bool:
        """Verilen cümle bu kısaltmaya uyuyor mu.

        Aday üretiminden sonraki geri kontrol adımı budur: model Türkçede
        kolayca "yakın ama yanlış" cümle üretir, bu filtre onları eler.

        İki taraf da normalleştirilir. S4'ün ek etiketleri büyük harfle
        üretilir ama kullanıcıdan küçük harfle gelebilir; tek tarafı
        normalleştirmek her S4 adayını sessizce geçersiz sayar.

        Açık yazılmış kelime de uyar: "su i" girdisinde "Su istiyorum."
        geçerlidir. Bu olmadan kullanıcı kelime yazdığı anda bütün adaylar
        geçersiz sayılıp arayüzden gizlenir.
        """
        words = tokenize(sentence)
        pieces = normalize_abbreviation(abbreviation).split()
        if len(words) != len(pieces):
            return False
        abbreviations = self.abbreviate_words(words)
        return all(
            piece in (word, normalize_abbreviation(abbreviation))
            for word, abbreviation, piece in zip(words, abbreviations, pieces, strict=True)
        )

    def keystrokes(self, sentence: str) -> int:
        """Kısaltmayı girmek için gereken seçim sayısı.

        Boşluklar sayılmaz: arayüzde kelime sınırı ayrı bir tuş değil, aday
        listesine geçişle örtülü olarak verilir.
        """
        return len(self.abbreviate(sentence).replace(" ", ""))


def normalize_abbreviation(abbreviation: str) -> str:
    """Kısaltmayı karşılaştırmaya hazır hale getirir.

    S4 etiketleri ``SUFFIX_TAGS`` sırasına dizilir ve tekrarları atılır:
    arayüzde kullanıcı etiketleri istediği sırayla seçer, "i-1s+neg+prog"
    ile "i-NEG+PROG+1S" aynı kısaltmadır.
    """
    return " ".join(_order_piece(piece) for piece in turkish_lower(abbreviation).split())


def order_tags(tags: Sequence[str]) -> list[str]:
    """Etiketleri ``SUFFIX_TAGS`` sırasına dizer; tekrarları atar.

    Tanımlı olmayan etiketler sona, geldikleri sırayla eklenir. Büyük-küçük
    harf korunur, sıralama büyük harfe göre yapılır.

    >>> order_tags(["1S", "NEG", "PROG", "NEG"])
    ['NEG', 'PROG', '1S']
    """
    rank = {tag: index for index, tag in enumerate(SUFFIX_TAGS)}
    unique = list(dict.fromkeys(tag for tag in tags if tag))
    return sorted(unique, key=lambda tag: rank.get(tag.upper(), len(rank)))


def _order_piece(piece: str) -> str:
    head, dash, tags = piece.partition("-")
    if not dash:
        return piece
    ordered = order_tags(tags.split("+"))
    return f"{head}-{'+'.join(ordered)}" if ordered else head


def canonical_abbreviation(abbreviation: str) -> str:
    """Dil modeline giden tek biçim: harfler küçük, S4 etiketleri büyük.

    Eğitim çiftleri kısaltmayı ``abbreviate`` ile üretir (``i-NEG+1S``), arayüz
    ve simülasyon ise küçültüp gönderir (``i-neg+1s``). İstem iki yoldan farklı
    çıkarsa ince ayarlı model, eğitimde hiç görmediği bir girdiyle karşılaşır.
    """
    pieces = []
    for piece in normalize_abbreviation(abbreviation).split():
        head, dash, tag = piece.partition("-")
        pieces.append(head + dash + tag.upper())
    return " ".join(pieces)


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


# Ek sınıfı etiketleri. Arayüzde her biri ayrı bir büyük hedef olur ve bir
# kelimeye birden çok etiket verilebilir. Sıra önemlidir: kısaltmada
# etiketler bu sırayla yazılır (``order_tags``).
#
# Liste 12 hedefli ızgaraya sığmak zorunda: son satır eylemlere ayrıldığı
# için 8 hücre kalıyor. Hal ekleri (-e, -de, -den, -i) bu yüzden dışarıda:
# kullanıcının dilbilgisi terimi olarak düşünmesi zor, model de çoğunu
# fiilden ve bağlamdan çıkarabiliyor ("ev gidiyorum" -> "eve gidiyorum").
SUFFIX_TAGS: dict[str, str] = {
    "NEG": "olumsuz",
    "PAST": "geçmiş zaman",
    "FUT": "gelecek zaman",
    "PROG": "şimdiki zaman",
    "Q": "soru",
    "1S": "1. tekil kişi",
    "2S": "2. tekil kişi",
    "PLUR": "çoğul",
}

# Kural tabanlı yaklaşık çözümleme. Asıl çözümleme Zemberek ile yapılır
# (morphology.py); bu tablo yalnızca Zemberek'in tanımadığı kelimelerde
# (özel ad, yazım hatası) kullanılır. Yalnızca kelime sonuna baktığı için
# tek başına güvenilmez: "kedi" sonundaki "di" yüzünden PAST alır.
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

    En bilgili şema: kullanıcı baş harfi girer, sonra kelimedeki ekleri
    etiket başına bir seçimle söyler ("istemiyorum" -> ``i-NEG+PROG+1S``).
    Tuş tasarrufu S1'den düşük ama belirsizlik çok daha az.

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
            tagger: ``tag(word) -> str`` arayüzü olan çözümleyici; varsa
                ``tag_sentence(words) -> list[str]`` ile cümle bağlamı da
                kullanılır. Verilmezse kural tabanlı tahmin kullanılır.
        """
        self._tagger = tagger

    @property
    def tagger(self) -> object | None:
        return self._tagger

    def _tag(self, word: str) -> str:
        if self._tagger is not None and hasattr(self._tagger, "tag"):
            return str(self._tagger.tag(word))
        return guess_suffix_tag(word)

    def _tags(self, words: Sequence[str]) -> list[str]:
        """Kelimelerin etiketleri, ``SUFFIX_TAGS`` sırasında ve yalnızca o kümeden."""
        if self._tagger is not None and hasattr(self._tagger, "tag_sentence"):
            raw = [str(tag) for tag in self._tagger.tag_sentence(words)]
        else:
            raw = [self._tag(word) for word in words]
        return ["+".join(t for t in order_tags(tag.split("+")) if t in SUFFIX_TAGS) for tag in raw]

    @staticmethod
    def _join(word: str, tag: str) -> str:
        return f"{word[:1]}-{tag}" if tag else word[:1]

    def abbreviate_word(self, word: str) -> str:
        return self.abbreviate_words([word])[0]

    def abbreviate_words(self, words: Sequence[str]) -> list[str]:
        return [self._join(w, t) for w, t in zip(words, self._tags(words), strict=True)]

    def keystrokes(self, sentence: str) -> int:
        """Etiket tek seçimle girilir, harf harf değil.

        Bu yüzden S4'ün maliyeti, kısaltma dizesinin karakter sayısı değil:
        kelime başına 1 harf + (varsa) etiket sayısı kadar seçimdir.
        """
        total = 0
        for tag in self._tags(tokenize(sentence)):
            total += 1
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


def warm_up_schemes() -> None:
    """Çözümleyici kullanan şemaları (S4 -> Zemberek) şimdi yükler.

    Zemberek'in yüklenmesi birkaç saniye sürer; ilk S4 isteğine kalırsa o
    isteğin gecikmesine eklenir.
    """
    for scheme in _REGISTRY.values():
        warm_up = getattr(getattr(scheme, "tagger", None), "warm_up", None)
        if callable(warm_up):
            warm_up()


def all_schemes() -> list[AbbreviationScheme]:
    """Kayıtlı tüm şemalar, kimlik sırasına göre."""
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


register(InitialScheme())
register(TwoLetterScheme())
register(FirstLastScheme())
register(SuffixTaggedScheme(ZemberekTagger(SUFFIX_TAGS, fallback=guess_suffix_tag)))
