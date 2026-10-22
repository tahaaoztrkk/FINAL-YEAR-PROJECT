"""Genişletme servisi, geri kontrol ve metriklerin testleri."""

from __future__ import annotations

import pytest

from gaze_aac.evaluation.metrics import (
    keystroke_savings_rate,
    mean_reciprocal_rank,
    top_k_accuracy,
)
from gaze_aac.evaluation.simulate import SimulationCase, run_condition
from gaze_aac.nlp.expander import ExpansionService, back_check
from gaze_aac.nlp.providers.mock import MockProvider
from gaze_aac.nlp.providers.ngram import NGramProvider
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
