"""S4 etiketleri için Zemberek çözümlemesinin testleri."""

from __future__ import annotations

import sys

import pytest

from gaze_aac.nlp.morphology import ZemberekTagger, _install_shims, tags_from_morphemes
from gaze_aac.nlp.schemes import SUFFIX_TAGS, get_scheme


@pytest.fixture(scope="module")
def tagger() -> ZemberekTagger:
    return ZemberekTagger(SUFFIX_TAGS)


class TestTagsFromMorphemes:
    def test_keeps_order_and_maps_person_and_possessive_to_one_tag(self) -> None:
        tags = tags_from_morphemes(["Noun", "A3pl", "P1sg", "Acc"], SUFFIX_TAGS)
        assert tags == "PLUR+1S"

    def test_same_tag_written_once(self) -> None:
        assert tags_from_morphemes(["Neg", "Unable"], SUFFIX_TAGS) == "NEG"

    def test_tags_outside_the_set_are_dropped(self) -> None:
        """Arayüzde olmayan etiketi kullanıcı giremez."""
        assert tags_from_morphemes(["Neg", "Prog1", "A1sg"], {"NEG", "1S"}) == "NEG+1S"


class TestZemberekTagger:
    @pytest.mark.parametrize(
        ("word", "expected"),
        [
            ("istemiyorum", "NEG+PROG+1S"),
            ("gelemeyeceğim", "NEG+FUT+1S"),
            ("telefonumu", "1S"),
            # Hal ekleri etiket kümesinde yok.
            ("hastaneden", ""),
            ("mısın", "Q+2S"),
            # Kural tablosu sondaki "di" yüzünden PAST verirdi.
            ("kedi", ""),
            ("daha", ""),
        ],
    )
    def test_word_tags(self, tagger: ZemberekTagger, word: str, expected: str) -> None:
        assert tagger.tag(word) == expected

    def test_bare_imperative_and_pronoun_get_no_tag(self, tagger: ZemberekTagger) -> None:
        """Görünür ek yoksa kullanıcı etiket eklemeyi düşünmez."""
        assert tagger.tag_sentence(["ben", "su", "sür"]) == ["", "", ""]

    def test_proper_noun_reading_is_avoided(self, tagger: ZemberekTagger) -> None:
        """'selam' küçük harfle yazılmış 'Sela' adının iyelikli hali değildir."""
        assert tagger.tag_sentence(["annene", "selam", "söyle"]) == ["2S", "", ""]

    def test_unknown_word_uses_fallback(self) -> None:
        tagger = ZemberekTagger(SUFFIX_TAGS, fallback=lambda word: "PLUR")
        assert tagger.tag("qxzvbn") == "PLUR"

    def test_fallback_tags_outside_the_set_are_dropped(self) -> None:
        tagger = ZemberekTagger(SUFFIX_TAGS, fallback=lambda word: "PLUR+DAT")
        assert tagger.tag("qxzvbn") == "PLUR"

    def test_empty_sentence(self, tagger: ZemberekTagger) -> None:
        assert tagger.tag_sentence([]) == []


class TestS4UsesZemberek:
    def test_registered_scheme_uses_morphology(self) -> None:
        scheme = get_scheme("S4")
        assert scheme.abbreviate("Telefonumu şarja takar mısın?") == "t-1S ş t m-Q+2S"

    def test_keystrokes_count_letter_plus_tags(self) -> None:
        assert get_scheme("S4").keystrokes("Telefonumu şarja takar mısın?") == 7

    def test_back_check_accepts_its_own_abbreviation(self) -> None:
        scheme = get_scheme("S4")
        sentence = "Yarın hastaneye gitmek istemiyorum."
        assert scheme.matches(sentence, scheme.abbreviate(sentence).lower())

    def test_tags_are_written_in_a_fixed_order(self) -> None:
        """Zemberek "kitap-lar-ım" sırasıyla PLUR+1S verir; kısaltma tek sıra kullanır."""
        assert get_scheme("S4").abbreviate("Kitaplarımı getirir misin?") == "k-1S+PLUR g m-Q+2S"

    def test_back_check_ignores_tag_order(self) -> None:
        """Arayüzde etiketler istenen sırayla seçilebilir."""
        scheme = get_scheme("S4")
        sentence = "Yarın hastaneye gitmek istemiyorum."
        assert scheme.matches(sentence, "y h g i-1s+prog+neg")
        assert not scheme.matches(sentence, "y h g i-1s+prog")

    def test_revealed_words_keep_context_tags(self) -> None:
        scheme = get_scheme("S4")
        sentence = "Yarın hastaneye gitmek istemiyorum."
        assert scheme.abbreviate_revealing(sentence, 1) == "yarın h g i-NEG+PROG+1S"


def test_shims_are_idempotent() -> None:
    _install_shims()
    _install_shims()
    assert "typing.io" in sys.modules
