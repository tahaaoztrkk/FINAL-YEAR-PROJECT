"""Genişletme servisi, geri kontrol ve metriklerin testleri."""

from __future__ import annotations

from pathlib import Path

import pytest

from gaze_aac.config import Settings
from gaze_aac.evaluation.metrics import (
    keystroke_savings_rate,
    mean_reciprocal_rank,
    top_k_accuracy,
)
from gaze_aac.evaluation.simulate import (
    SimulationCase,
    context_options_for,
    run_condition,
    simulate_case,
)
from gaze_aac.nlp.expander import ExpansionService, back_check, build_provider, default_corpus_path
from gaze_aac.nlp.providers.hf_local import HuggingFaceProvider
from gaze_aac.nlp.providers.mock import MockProvider
from gaze_aac.nlp.providers.ngram import NGramProvider
from gaze_aac.nlp.schemes import get_scheme
from gaze_aac.schemas.expansion import Candidate, ExpansionRequest


class TestBackCheck:
    def test_marks_matching_candidate_valid(self) -> None:
        request = ExpansionRequest(abbreviation="s i", scheme="S1")
        checked = back_check([Candidate(text="Su istiyorum.")], request)
        assert checked[0].valid

    def test_marks_mismatching_candidate_invalid(self) -> None:
        """Model Türkçede kolayca 'yakın ama yanlış' cümle üretir;
        bu filtre olmadan yanlış adaylar listeye sızar."""
        request = ExpansionRequest(abbreviation="s i", scheme="S1")
        checked = back_check([Candidate(text="Su içmek istiyorum.")], request)
        assert not checked[0].valid

    def test_spelled_out_word_keeps_candidate_valid(self) -> None:
        """Arayüz geçersiz adayı gizler; açık yazılan kelime adayı düşürmemeli."""
        request = ExpansionRequest(abbreviation="su i", scheme="S1")
        checked = back_check([Candidate(text="Su istiyorum.")], request)
        assert checked[0].valid


class TestExpansionService:
    async def test_returns_matching_sentence(self) -> None:
        service = ExpansionService(MockProvider())
        result = await service.expand(ExpansionRequest(abbreviation="s i", scheme="S1"))

        assert result.provider == "mock"
        assert any(c.text == "Su istiyorum." for c in result.candidates)

    async def test_valid_candidates_come_first(self) -> None:
        service = ExpansionService(MockProvider())
        result = await service.expand(ExpansionRequest(abbreviation="s i", scheme="S1", top_k=5))

        validity = [c.valid for c in result.candidates]
        assert validity == sorted(validity, reverse=True)

    async def test_respects_top_k(self) -> None:
        service = ExpansionService(MockProvider())
        result = await service.expand(ExpansionRequest(abbreviation="b", scheme="S1", top_k=2))
        assert len(result.candidates) <= 2

    async def test_latency_is_measured(self) -> None:
        service = ExpansionService(MockProvider())
        result = await service.expand(ExpansionRequest(abbreviation="s i", scheme="S1"))
        assert result.latency_ms >= 0.0


class TestNGramProvider:
    async def test_produces_candidates_after_fitting(self) -> None:
        provider = NGramProvider()
        provider.fit(["Su istiyorum", "Su içmek istiyorum", "Yemek istiyorum"])

        result = await provider.expand(ExpansionRequest(abbreviation="s i", scheme="S1"))
        assert result
        assert all(isinstance(c.text, str) for c in result)

    async def test_empty_model_returns_nothing(self) -> None:
        provider = NGramProvider()
        assert await provider.expand(ExpansionRequest(abbreviation="s i")) == []

    async def test_known_sentence_keeps_original_spelling(self) -> None:
        """Derlemdeki cümle noktalaması ve Türkçe büyük harfiyle döner."""
        provider = NGramProvider()
        provider.fit(["İlacımın saati geldi.", "Su istiyorum."])

        result = await provider.expand(ExpansionRequest(abbreviation="i s g", scheme="S1"))
        assert result[0].text == "İlacımın saati geldi."

    async def test_s4_tags_match_lowercase_input(self) -> None:
        """S4 etiketleri büyük harfle üretilir, kullanıcıdan küçük harfle gelir."""
        provider = NGramProvider()
        provider.fit(["Gelmeyeceğim."])
        abbreviation = get_scheme("S4").abbreviate("Gelmeyeceğim.").lower()

        result = await provider.expand(ExpansionRequest(abbreviation=abbreviation, scheme="S4"))
        assert result and result[0].text == "Gelmeyeceğim."

    async def test_spelled_out_word_is_used_as_is(self) -> None:
        """Açık yazılan kelime, derlemde olmasa da adayın içine girer."""
        provider = NGramProvider()
        provider.fit(["Su istiyorum."])

        result = await provider.expand(ExpansionRequest(abbreviation="çay i", scheme="S1"))
        assert result and result[0].text == "Çay istiyorum"


class TestHuggingFaceProviderName:
    """Model yüklenmez; ad yalnızca sonuç tablosundaki satırı belirler."""

    def test_zero_shot_and_fine_tuned_are_separate_rows(self) -> None:
        assert HuggingFaceProvider("model").name == "hf_local"
        assert HuggingFaceProvider("model", adapter_path="adaptor").name == "hf_local+lora"


class TestBuildProvider:
    def test_ngram_loads_repo_corpus_by_default(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus" / "aac_sentences.jsonl"
        corpus.parent.mkdir()
        corpus.write_text('{"text": "Su istiyorum."}\n', encoding="utf-8")
        settings = Settings(data_dir=tmp_path)

        provider = build_provider("ngram", settings)
        assert isinstance(provider, NGramProvider)
        assert default_corpus_path(settings) == corpus


class TestMockProvider:
    async def test_s4_matches_lowercase_input(self) -> None:
        provider = MockProvider()
        abbreviation = get_scheme("S4").abbreviate("Su istiyorum.").lower()

        result = await provider.expand(ExpansionRequest(abbreviation=abbreviation, scheme="S4"))
        assert any(c.text == "Su istiyorum." for c in result)


class TestMetrics:
    def test_ksr_formula(self) -> None:
        # 20 karakterlik cümle 5 seçimle yazıldıysa %75 tasarruf
        assert keystroke_savings_rate(5, 20) == pytest.approx(75.0)

    def test_ksr_no_saving(self) -> None:
        assert keystroke_savings_rate(20, 20) == pytest.approx(0.0)

    def test_ksr_handles_zero_denominator(self) -> None:
        assert keystroke_savings_rate(0, 0) == 0.0

    def test_top_k_accuracy(self) -> None:
        ranks: list[int | None] = [0, 2, None, 1]
        assert top_k_accuracy(ranks, 1) == pytest.approx(25.0)
        assert top_k_accuracy(ranks, 5) == pytest.approx(75.0)

    def test_mrr_rewards_higher_rank(self) -> None:
        assert mean_reciprocal_rank([0]) > mean_reciprocal_rank([4])

    def test_mrr_ignores_misses_as_zero(self) -> None:
        assert mean_reciprocal_rank([None, None]) == 0.0


class TestSimulation:
    async def test_condition_produces_stats(self) -> None:
        cases = [
            SimulationCase(text="Su istiyorum."),
            SimulationCase(text="Teşekkür ederim."),
        ]
        service = ExpansionService(MockProvider())
        stats = await run_condition(cases, service, "S1", top_k=5)

        assert stats.sentence_count == 2
        assert stats.total_characters > 0
        assert stats.scheme == "S1"
        assert 0.0 <= stats.top5 <= 100.0

    async def test_csv_row_has_report_columns(self) -> None:
        service = ExpansionService(MockProvider())
        stats = await run_condition([SimulationCase(text="Su istiyorum.")], service, "S1")

        row = stats.as_row()
        assert set(row) == {
            "sema",
            "saglayici",
            "baglam",
            "cumle_sayisi",
            "ksr",
            "ilk1",
            "ilk5",
            "mrr",
            "gecikme_ms",
        }


class _FoundAfterReveal:
    """Hedef cümleyi yalnızca en az bir kelime açık yazılınca bulan sağlayıcı."""

    name = "test"

    def __init__(self, sentence: str) -> None:
        self.sentence = sentence

    async def expand(self, request: ExpansionRequest) -> list[Candidate]:
        plain = get_scheme(request.scheme).abbreviate(self.sentence).lower()
        if request.abbreviation == plain:
            return []
        return [Candidate(text=self.sentence)]


class TestRevealCost:
    sentence = "Yarın hastaneye gitmek istemiyorum."

    @pytest.mark.parametrize("scheme_id", ["S1", "S2", "S3", "S4"])
    async def test_revealed_word_costs_its_letters_minus_its_abbreviation(
        self, scheme_id: str
    ) -> None:
        """'Yarın' açık yazılınca 5 harf girilir, kısaltmasının seçimleri düşer.

        Eskiden kısaltma her şemada 1 seçim sayılıyordu; bu S2-S4'ü haksız
        yere cezalandırıyordu.
        """
        scheme = get_scheme(scheme_id)
        service = ExpansionService(_FoundAfterReveal(self.sentence))

        selections, rank, _ = await simulate_case(
            SimulationCase(text=self.sentence), service, scheme_id, top_k=5, use_context=False
        )

        assert rank == 0
        expected_extra = len("yarın") - scheme.keystrokes("yarın")
        assert selections == scheme.keystrokes(self.sentence) + expected_extra + 1


class TestContextOptions:
    def test_without_context_only_one_condition(self) -> None:
        assert context_options_for([SimulationCase(text="Su istiyorum.")]) == (False,)

    def test_with_context_both_conditions(self) -> None:
        cases = [SimulationCase(text="Evet.", context="Su ister misin?")]
        assert context_options_for(cases) == (False, True)
