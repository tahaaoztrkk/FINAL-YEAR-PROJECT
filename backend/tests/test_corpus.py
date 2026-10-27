"""Derlem yükleme ve bölme testleri.

Bölmedeki sızıntı sonuçları sessizce şişirir: aynı anlamdaki iki cümleden
biri eğitime, diğeri doğrulamaya düşerse model ezberden kazanmış görünür.
"""

from __future__ import annotations

from pathlib import Path

from gaze_aac.config import Settings
from gaze_aac.data.corpus import Corpus, CorpusEntry


def _corpus_with_groups() -> Corpus:
    entries = [CorpusEntry(text=f"Cümle {i}.") for i in range(40)]
    entries += [
        CorpusEntry(text="Su istiyorum.", group="su"),
        CorpusEntry(text="Susadım.", group="su"),
        CorpusEntry(text="Uyumak istiyorum.", group="uyku"),
        CorpusEntry(text="Uykum geldi.", group="uyku"),
    ]
    return Corpus(entries)


class TestSplit:
    def test_group_members_land_in_same_part(self) -> None:
        # Tohum ne olursa olsun grup bölünmemeli.
        for seed in range(20):
            parts = _corpus_with_groups().split(seed=seed)
            for group in ("su", "uyku"):
                holding = [
                    index
                    for index, part in enumerate(parts)
                    if any(entry.group == group for entry in part.entries)
                ]
                assert len(holding) == 1, (seed, group, holding)

    def test_every_entry_is_kept_once(self) -> None:
        corpus = _corpus_with_groups()
        parts = corpus.split()
        texts = [entry.text for part in parts for entry in part.entries]
        assert sorted(texts) == sorted(entry.text for entry in corpus.entries)

    def test_same_seed_same_split(self) -> None:
        first = [len(part) for part in _corpus_with_groups().split(seed=7)]
        second = [len(part) for part in _corpus_with_groups().split(seed=7)]
        assert first == second


class TestRoundTrip:
    def test_group_survives_save_and_load(self, tmp_path: Path) -> None:
        path = tmp_path / "derlem.jsonl"
        Corpus([CorpusEntry(text="Susadım.", category="temel_ihtiyac", group="su")]).save(path)

        loaded = Corpus.load(path)
        assert loaded.entries[0].group == "su"
        assert loaded.entries[0].category == "temel_ihtiyac"

    def test_note_survives_save_and_load(self, tmp_path: Path) -> None:
        path = tmp_path / "derlem.jsonl"
        Corpus([CorpusEntry(text="Susadım.", group="su", note="çıkarılacak")]).save(path)
        assert Corpus.load(path).entries[0].note == "çıkarılacak"


class TestRepoCorpus:
    def test_groups_have_at_least_two_members(self) -> None:
        """Tek üyeli grup, yazım hatası yapılmış bir grup adına işaret eder."""
        corpus = Corpus.load(Settings().source_corpus_path)
        counts: dict[str, int] = {}
        for entry in corpus.entries:
            if entry.group:
                counts[entry.group] = counts.get(entry.group, 0) + 1
        assert counts
        assert all(count >= 2 for count in counts.values()), counts

    def test_each_group_keeps_one_unmarked_sentence(self) -> None:
        """Her gruptan tam bir cümle kalır, diğerleri 'çıkarılacak' işaretlidir."""
        corpus = Corpus.load(Settings().source_corpus_path)
        kept: dict[str, int] = {}
        for entry in corpus.entries:
            if entry.group:
                kept.setdefault(entry.group, 0)
                if not entry.note:
                    kept[entry.group] += 1
        assert all(count == 1 for count in kept.values()), kept
