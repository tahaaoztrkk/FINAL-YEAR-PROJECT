"""İnce ayar veri hazırlığının testleri.

GPU ve model gerekmez. Eğitimin sessizce bozulduğu yerler veri tarafında:
istemin kayba katılması, EOS'un unutulması, doğrulama cümlelerinin eğitime
sızması.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gaze_aac.data.corpus import Corpus, CorpusEntry, build_training_pairs, write_pairs
from gaze_aac.nlp.finetune import (
    IGNORE_INDEX,
    Hyperparameters,
    TrainingExample,
    encode_example,
    encode_examples,
    find_leaks,
    load_examples,
    main,
    plan_steps,
)


class FakeTokenizer:
    """Her karakteri bir belirteç sayan, istemin başına BOS koyan tokenizer."""

    bos_token_id = 2
    eos_token_id: int | None = 1

    def __call__(self, text: str, *, add_special_tokens: bool = True) -> dict[str, list[int]]:
        ids = [ord(character) for character in text]
        return {"input_ids": [self.bos_token_id, *ids] if add_special_tokens else ids}


def _write_corpus(path: Path, sentences: list[str]) -> None:
    Corpus([CorpusEntry(text=sentence) for sentence in sentences]).save(path)


class TestHyperparameters:
    def test_defaults_follow_technical_plan(self) -> None:
        plan = Hyperparameters()
        assert (plan.lora_r, plan.lora_alpha) == (16, 32)
        assert plan.learning_rate == pytest.approx(2e-4)
        assert plan.epochs == 3
        assert (plan.batch_size, plan.grad_accum, plan.effective_batch) == (4, 4, 16)
        # Plandaki 256'dan kısa olmamalı; uzun S4 istemleri atılmasın.
        assert plan.max_length >= 256

    def test_plan_steps(self) -> None:
        per_epoch, total, warmup = plan_steps(1158, Hyperparameters())
        assert (per_epoch, total) == (73, 219)
        assert 1 <= warmup < total


class TestEncode:
    example = TrainingExample(prompt="Kısaltma: s i\nCümle:", completion=" Su istiyorum.")

    def test_loss_only_on_completion_and_eos(self) -> None:
        tokenizer = FakeTokenizer()
        encoded = encode_example(self.example, tokenizer, max_length=256)
        assert encoded is not None

        prompt_length = len(self.example.prompt) + 1  # BOS dahil
        assert encoded["labels"][:prompt_length] == [IGNORE_INDEX] * prompt_length
        completion = [ord(character) for character in self.example.completion]
        assert encoded["labels"][prompt_length:] == [*completion, tokenizer.eos_token_id]

    def test_prompt_is_encoded_like_inference(self) -> None:
        """Çıkarımda hf_local istemi özel belirteçlerle kodlar; eğitim de öyle."""
        tokenizer = FakeTokenizer()
        encoded = encode_example(self.example, tokenizer, max_length=256)
        assert encoded is not None
        prompt_ids = tokenizer(self.example.prompt)["input_ids"]
        assert encoded["input_ids"][: len(prompt_ids)] == prompt_ids
        assert encoded["attention_mask"] == [1] * len(encoded["input_ids"])

    def test_too_long_example_is_dropped_not_truncated(self) -> None:
        features, dropped = encode_examples([self.example], FakeTokenizer(), max_length=10)
        assert features == []
        assert dropped == 1

    def test_no_eos_token(self) -> None:
        tokenizer = FakeTokenizer()
        tokenizer.eos_token_id = None
        encoded = encode_example(self.example, tokenizer, max_length=256)
        assert encoded is not None
        assert encoded["labels"][-1] == ord(".")


class TestLoadExamples:
    def test_reads_what_build_corpus_writes(self, tmp_path: Path) -> None:
        path = tmp_path / "pairs.jsonl"
        corpus = Corpus([CorpusEntry(text="Su istiyorum."), CorpusEntry(text="Başım ağrıyor.")])
        write_pairs(build_training_pairs(corpus, reveal_share=1.0), path)

        examples = load_examples(path)
        assert {example.scheme for example in examples} == {"S1", "S2", "S3", "S4"}
        assert all(example.completion == f" {example.sentence}" for example in examples)
        assert any(example.revealed for example in examples)

    def test_bad_line_reports_line_number(self, tmp_path: Path) -> None:
        path = tmp_path / "pairs.jsonl"
        path.write_text('{"prompt": "p", "completion": " c"}\n{"prompt": "p"}\n', encoding="utf-8")
        with pytest.raises(ValueError, match=":2"):
            load_examples(path)

    def test_limit(self, tmp_path: Path) -> None:
        path = tmp_path / "pairs.jsonl"
        write_pairs(build_training_pairs(Corpus([CorpusEntry(text="Su istiyorum.")])), path)
        assert len(load_examples(path, limit=2)) == 2


class TestLeaks:
    def test_detects_sentence_in_held_out_set(self, tmp_path: Path) -> None:
        held_out = tmp_path / "val.jsonl"
        _write_corpus(held_out, ["su istiyorum", "Başım ağrıyor."])
        examples = [
            TrainingExample(prompt="p", completion=" Su istiyorum.", sentence="Su istiyorum.")
        ]

        assert find_leaks(examples, [held_out]) == {held_out: 1}

    def test_missing_file_is_skipped(self, tmp_path: Path) -> None:
        assert find_leaks([], [tmp_path / "yok.jsonl"]) == {}


class TestCommandLine:
    @pytest.fixture
    def data_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        processed = tmp_path / "processed"
        processed.mkdir()
        train = Corpus([CorpusEntry(text="Su istiyorum."), CorpusEntry(text="Başım ağrıyor.")])
        write_pairs(build_training_pairs(train), processed / "training_pairs.jsonl")
        _write_corpus(processed / "val.jsonl", ["Doktoru çağırır mısın?"])
        _write_corpus(processed / "test.jsonl", ["Saat kaç?"])
        return tmp_path

    def test_dry_run_needs_no_model_libraries(
        self, data_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["--dry-run"])

        output = capsys.readouterr().out
        assert "Sızıntı denetimi temiz" in output
        assert "Kuru çalıştırma bitti" in output
        assert "torch" not in sys.modules
        assert not (data_dir.parent / "models").exists()

    def test_refuses_to_train_on_leaked_split(self, data_dir: Path) -> None:
        _write_corpus(data_dir / "processed" / "val.jsonl", ["Su istiyorum."])
        with pytest.raises(SystemExit, match="Sızıntı"):
            main(["--dry-run"])

    def test_missing_pairs_explains_next_step(self, data_dir: Path) -> None:
        (data_dir / "processed" / "training_pairs.jsonl").unlink()
        with pytest.raises(SystemExit, match="build_corpus"):
            main(["--dry-run"])
