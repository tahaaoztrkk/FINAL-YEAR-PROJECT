"""Kısaltma şemalarının testleri.

Bu testler projenin araştırma sorusunu koruyor: şema kuralları sessizce
değişirse simülasyon sonuçları karşılaştırılamaz hale gelir.
"""

from __future__ import annotations

import pytest

from gaze_aac.nlp.schemes import (
    FirstLastScheme,
    InitialScheme,
    SuffixTaggedScheme,
    TwoLetterScheme,
    all_schemes,
    canonical_abbreviation,
    get_scheme,
    guess_suffix_tag,
    tokenize,
    turkish_capitalize,
    turkish_lower,
)


class TestTurkishLower:
    def test_dotted_and_dotless_i(self) -> None:
        # str.lower() burada yanlış yapar: "I".lower() == "i" olur,
        # Türkçede "I" -> "ı" olmalı.
        assert turkish_lower("İSTANBUL") == "istanbul"
        assert turkish_lower("IŞIK") == "ışık"
        assert turkish_lower("Iğdır") == "ığdır"

    def test_other_turkish_letters(self) -> None:
        assert turkish_lower("ÇĞÖŞÜ") == "çğöşü"


class TestTurkishCapitalize:
    def test_dotted_and_dotless_i(self) -> None:
        assert turkish_capitalize("istiyorum") == "İstiyorum"
        assert turkish_capitalize("ılık") == "Ilık"

    def test_rest_is_unchanged(self) -> None:
        assert turkish_capitalize("su İstiyorum") == "Su İstiyorum"


class TestTokenize:
    def test_strips_punctuation(self) -> None:
        assert tokenize("Su istiyorum.") == ["su", "istiyorum"]

    def test_handles_question_and_commas(self) -> None:
        assert tokenize("Doktoru çağırır mısın?") == ["doktoru", "çağırır", "mısın"]

    def test_drops_digits(self) -> None:
        assert tokenize("Saat 3 oldu") == ["saat", "oldu"]

    def test_empty(self) -> None:
        assert tokenize("...") == []


class TestInitialScheme:
    scheme = InitialScheme()

    def test_abbreviate(self) -> None:
        assert self.scheme.abbreviate("Su istiyorum.") == "s i"
        assert self.scheme.abbreviate("Yarın hastaneye gitmek istemiyorum.") == "y h g i"

    def test_keystrokes_excludes_spaces(self) -> None:
        assert self.scheme.keystrokes("Yarın hastaneye gitmek istemiyorum.") == 4

    def test_matches_ignores_case_and_punctuation(self) -> None:
        assert self.scheme.matches("Su istiyorum.", "s i")
        assert self.scheme.matches("SU İSTİYORUM", "s i")
        assert not self.scheme.matches("Su istemiyorum.", "s a")


class TestRevealedWords:
    """Kullanıcı doğru cümleyi bulamayınca baştan birer kelime açık yazar."""

    sentence = "Yarın hastaneye gitmek istemiyorum."

    def test_abbreviate_revealing(self) -> None:
        assert InitialScheme().abbreviate_revealing(self.sentence, 2) == "yarın hastaneye g i"
        assert InitialScheme().abbreviate_revealing(self.sentence, 0) == "y h g i"

    def test_s4_keeps_tags_on_hidden_words(self) -> None:
        revealed = SuffixTaggedScheme().abbreviate_revealing(self.sentence, 1)
        assert revealed == "yarın h-DAT g i-NEG+PROG+1S"

    @pytest.mark.parametrize("scheme_id", ["S1", "S2", "S3", "S4"])
    def test_back_check_accepts_revealed_words(self, scheme_id: str) -> None:
        """Yoksa kullanıcı kelime yazdığı anda bütün adaylar gizlenir."""
        scheme = get_scheme(scheme_id)
        for count in range(5):
            abbreviation = scheme.abbreviate_revealing(self.sentence, count).lower()
            assert scheme.matches(self.sentence, abbreviation), abbreviation

    def test_back_check_still_rejects_wrong_words(self) -> None:
        scheme = InitialScheme()
        assert not scheme.matches("Su istiyorum.", "çay i")
        assert not scheme.matches("Su istiyorum.", "su i a")


class TestCanonicalAbbreviation:
    def test_letters_lower_tags_upper(self) -> None:
        assert canonical_abbreviation("Y h-dat g-fut+1s") == "y h-DAT g-FUT+1S"

    def test_generated_form_is_unchanged(self) -> None:
        abbreviation = SuffixTaggedScheme().abbreviate("Yarın hastaneye gitmek istemiyorum.")
        assert canonical_abbreviation(abbreviation) == abbreviation

    def test_schemes_without_tags(self) -> None:
        assert canonical_abbreviation("  YA  ha ") == "ya ha"


class TestTwoLetterScheme:
    scheme = TwoLetterScheme()

    def test_abbreviate(self) -> None:
        assert self.scheme.abbreviate("Yarın hastaneye gitmek istemiyorum.") == "ya ha gi is"

    def test_single_letter_word(self) -> None:
        assert self.scheme.abbreviate_word("o") == "o"


class TestFirstLastScheme:
    scheme = FirstLastScheme()

    def test_abbreviate(self) -> None:
        assert self.scheme.abbreviate("Yarın hastaneye gitmek istemiyorum.") == "yn he gk im"

    def test_single_letter_word_not_duplicated(self) -> None:
        assert self.scheme.abbreviate_word("o") == "o"


class TestSuffixTaggedScheme:
    scheme = SuffixTaggedScheme()

    def test_tags_negation_and_progressive(self) -> None:
        # "istemiyorum" = iste + me + yor + um
        assert guess_suffix_tag("istemiyorum") == "NEG+PROG+1S"

    def test_tags_past(self) -> None:
        assert guess_suffix_tag("geldim") == "PAST+1S"

    def test_root_without_suffix_has_no_tag(self) -> None:
        assert guess_suffix_tag("su") == ""
        assert self.scheme.abbreviate_word("su") == "s"

    def test_keystrokes_count_tags_as_one_selection_each(self) -> None:
        # "istemiyorum" -> 1 harf + 3 etiket = 4 seçim
        assert self.scheme.keystrokes("istemiyorum") == 4

    def test_costs_more_than_initial_scheme(self) -> None:
        sentence = "Yarın hastaneye gitmek istemiyorum."
        assert self.scheme.keystrokes(sentence) > InitialScheme().keystrokes(sentence)


class TestRegistry:
    def test_all_four_schemes_registered(self) -> None:
        assert {s.id for s in all_schemes()} == {"S1", "S2", "S3", "S4"}

    def test_lookup_is_case_insensitive(self) -> None:
        assert get_scheme("s1").id == "S1"

    def test_unknown_scheme_lists_known_ones(self) -> None:
        with pytest.raises(KeyError, match="S1"):
            get_scheme("S9")


@pytest.mark.parametrize("scheme_id", ["S1", "S2", "S3", "S4"])
def test_round_trip_matches_itself(scheme_id: str) -> None:
    """Her şema, kendi ürettiği kısaltmayla cümleyi eşleştirebilmeli.

    Geri kontrol adımının temeli bu; bozulursa her aday geçersiz sayılır ve
    sistem hiçbir cümle üretemez.
    """
    scheme = get_scheme(scheme_id)
    sentence = "Yarın hastaneye gitmek istemiyorum."
    assert scheme.matches(sentence, scheme.abbreviate(sentence))
