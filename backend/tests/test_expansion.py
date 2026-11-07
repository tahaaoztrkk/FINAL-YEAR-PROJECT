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
    warm_up_services,
)
from gaze_aac.nlp.expander import ExpansionService, back_check, build_provider, default_corpus_path
from gaze_aac.nlp.providers.hf_local import (
    HuggingFaceProvider,
    dtype_kwargs,
    generation_kwargs,
    supports_bf16,
)
from gaze_aac.nlp.providers.llamacpp import LlamaCppProvider, candidates_from_texts
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
            "istek_ms",
            "istek_ms_en_cok",
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


class _FakeCuda:
    def __init__(self, available: bool, capability: tuple[int, int]) -> None:
        self._available = available
        self._capability = capability

    def is_available(self) -> bool:
        return self._available

    def get_device_capability(self) -> tuple[int, int]:
        return self._capability

    def is_bf16_supported(self) -> bool:
        # T4'te torch bunu taklit yüzünden True dönebilir; kullanılmamalı.
        return True


class _FakeTorch:
    def __init__(self, available: bool, capability: tuple[int, int]) -> None:
        self.cuda = _FakeCuda(available, capability)


class TestPrecision:
    def test_t4_uses_fp16_even_if_torch_claims_bf16(self) -> None:
        assert not supports_bf16(_FakeTorch(True, (7, 5)))

    def test_ampere_and_later_use_bf16(self) -> None:
        assert supports_bf16(_FakeTorch(True, (8, 0)))
        assert supports_bf16(_FakeTorch(True, (8, 9)))

    def test_no_gpu_is_not_bf16(self) -> None:
        assert not supports_bf16(_FakeTorch(False, (0, 0)))

    def test_dtype_argument_name_follows_transformers_version(self) -> None:
        assert dtype_kwargs("4.46.3", "fp16") == {"torch_dtype": "fp16"}
        assert dtype_kwargs("5.0.0", "fp16") == {"dtype": "fp16"}


class _WarmableProvider(MockProvider):
    def __init__(self) -> None:
        super().__init__(None)
        self.warmed = 0

    def warm_up(self) -> None:
        self.warmed += 1


class TestWarmUp:
    def test_providers_with_warm_up_are_loaded_once(self) -> None:
        warmable = _WarmableProvider()
        services = {
            "big": ExpansionService(warmable),
            "plain": ExpansionService(MockProvider(None)),
        }
        warm_up_services(services)
        assert warmable.warmed == 1


class TestGenerationSettings:
    def test_default_keeps_beam_sampling(self) -> None:
        kwargs = generation_kwargs("beam_sample", 5, 24)
        assert kwargs["do_sample"] is True
        assert kwargs["num_beams"] == 5
        assert kwargs["num_return_sequences"] == 5
        assert kwargs["max_new_tokens"] == 24

    def test_beams_never_fewer_than_candidates(self) -> None:
        assert generation_kwargs("beam", 5, 24, num_beams=3)["num_beams"] == 5
        assert generation_kwargs("beam", 3, 24, num_beams=3)["num_beams"] == 3
        assert generation_kwargs("beam", 3, 24)["num_beams"] == 4

    def test_sample_and_greedy_use_no_beams(self) -> None:
        sample = generation_kwargs("sample", 5, 24)
        assert sample["num_beams"] == 1 and sample["num_return_sequences"] == 5
        greedy = generation_kwargs("greedy", 5, 24)
        assert greedy["do_sample"] is False and greedy["num_return_sequences"] == 1

    def test_unknown_decoding_fails_before_model_load(self) -> None:
        with pytest.raises(ValueError):
            HuggingFaceProvider("model", decoding="hizli")

    def test_settings_reach_provider(self) -> None:
        settings = Settings(
            expander_provider="hf_local", hf_max_new_tokens=16, hf_decoding="beam", hf_num_beams=3
        )
        provider = build_provider("hf_local", settings)
        assert isinstance(provider, HuggingFaceProvider)
        assert (provider.max_new_tokens, provider.decoding, provider.num_beams) == (16, "beam", 3)


class TestRequestLatency:
    async def test_each_model_call_is_recorded(self) -> None:
        stats = await run_condition(
            [SimulationCase(text="Su istiyorum.")],
            ExpansionService(MockProvider(None)),
            "S1",
        )
        assert len(stats.request_latencies_ms) >= 1
        row = stats.as_row()
        assert "istek_ms" in row and "istek_ms_en_cok" in row


class TestLlamaCppProvider:
    @staticmethod
    def _server(replies: list[str], seen: list[dict[str, object]]) -> object:
        import json

        import httpx

        def handle(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/completion"
            body = json.loads(request.content)
            seen.append(body)
            return httpx.Response(200, json={"content": replies[int(body["seed"])]})

        return httpx.MockTransport(handle)

    async def test_uses_the_training_prompt_without_chat_template(self) -> None:
        seen: list[dict[str, object]] = []
        provider = LlamaCppProvider(
            transport=self._server([" Su istiyorum.", " Su içiyorum."], seen)
        )
        request = ExpansionRequest(abbreviation="s i", scheme="S1", top_k=2)
        candidates = await provider.expand(request)

        assert [c.text for c in candidates] == ["Su istiyorum.", "Su içiyorum."]
        assert candidates[0].score > candidates[1].score
        from gaze_aac.nlp.prompts import build_prompt

        assert all(body["prompt"] == build_prompt("s i", scheme="S1") for body in seen)
        assert {body["temperature"] for body in seen} == {0.0, 0.7}
        assert all(body["stop"] == ["\n"] for body in seen)

    async def test_duplicates_and_blank_lines_are_dropped(self) -> None:
        seen: list[dict[str, object]] = []
        provider = LlamaCppProvider(
            transport=self._server(["Tamam.", "Tamam.", "  ", "Olur.\nfazla"], seen)
        )
        candidates = await provider.expand(ExpansionRequest(abbreviation="t", scheme="S1", top_k=4))
        assert [c.text for c in candidates] == ["Tamam.", "Olur."]

    def test_texts_keep_order_as_score(self) -> None:
        scores = [c.score for c in candidates_from_texts(["a", "b", "c"])]
        assert scores == sorted(scores, reverse=True)

    def test_built_from_settings(self) -> None:
        settings = Settings(llamacpp_url="http://127.0.0.1:9090/", llamacpp_max_tokens=16)
        provider = build_provider("llamacpp", settings)
        assert isinstance(provider, LlamaCppProvider)
        assert provider.base_url == "http://127.0.0.1:9090"
        assert provider.payload("x", 0)["n_predict"] == 16

    def test_warm_up_explains_missing_server(self) -> None:
        provider = LlamaCppProvider(base_url="http://127.0.0.1:9")
        with pytest.raises(RuntimeError, match="llama-server"):
            provider.warm_up()
