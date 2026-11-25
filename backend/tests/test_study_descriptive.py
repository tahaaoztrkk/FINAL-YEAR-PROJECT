"""Kullanıcı testinin betimsel analizi (ön kayıt, Bölüm 3.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gaze_aac.evaluation.metrics import words_per_minute
from gaze_aac.evaluation.study import SessionInfo, SurveyResult, TrialResult, load_study
from gaze_aac.evaluation.study_descriptive import (
    condition_result,
    condition_summary,
    faster_with_b,
    main,
    participant_table,
)
from tests.test_study import _trial_events, _write_session

TARGET = "Ellerim çok soğuk."  # 17 karakter (noktalamasız) -> 16/5 kelime


def _trial(
    participant: str = "K01",
    condition: str = "A",
    *,
    index: int = 0,
    seconds: float | None = 32.0,
    outcome: str = "done",
    practice: bool = False,
    deletes: int = 0,
) -> TrialResult:
    return TrialResult(
        participant=participant,
        block_index=0 if condition == "A" else 1,
        trial_index=index,
        condition=condition,
        scheme="S1",
        target=TARGET,
        practice=practice,
        outcome=outcome,
        correct=outcome == "done",
        duration_s=seconds,
        selections=10,
        deletes=deletes,
        backs=0,
        wrong_outputs=0,
        expands=0,
        candidate_rank=None,
        source="test",
    )


class TestConditionResult:
    def test_practice_is_left_out(self) -> None:
        result = condition_result(
            [_trial(seconds=32.0), _trial(index=1, seconds=1.0, practice=True)]
        )
        assert result.counted == 1
        assert result.wpm == pytest.approx(words_per_minute(TARGET, 32.0))

    def test_skipped_left_out_of_mean_but_counted_with_penalty(self) -> None:
        trials = [
            _trial(index=0, seconds=32.0),
            _trial(index=1, seconds=None, outcome="skipped"),
        ]
        result = condition_result(trials, skip_penalty_s=180.0)

        assert result.skipped == 1
        assert result.wpm == pytest.approx(words_per_minute(TARGET, 32.0))
        expected = (words_per_minute(TARGET, 32.0) + words_per_minute(TARGET, 180.0)) / 2
        assert result.wpm_penalized == pytest.approx(expected)
        # Ceza, atlamaların ortalamayı iyimser göstermesini düzeltir: hep daha yavaş.
        assert result.wpm_penalized is not None and result.wpm is not None
        assert result.wpm_penalized < result.wpm

    def test_corrections_are_mean_per_counted_sentence(self) -> None:
        result = condition_result([_trial(deletes=2), _trial(index=1, deletes=4)])
        assert result.corrections == pytest.approx(3.0)

    def test_empty_condition(self) -> None:
        result = condition_result([])
        assert result.wpm is None and result.wpm_penalized is None and result.counted == 0


class TestParticipantTable:
    def test_ratio_order_sus_and_calibration(self) -> None:
        trials = [_trial("K02", "A", seconds=40.0), _trial("K02", "B", seconds=20.0)]
        infos = [
            SessionInfo(
                participant="K02",
                source="x",
                order="BA",
                provider="llamacpp",
                scheme="S1",
                materials="55630ed3d54f",
                calibration_deg=2.25,
            )
        ]
        survey = [SurveyResult(participant="K02", sus=72.5, extra={})]

        (row,) = participant_table(trials, infos, survey)

        assert row["katilimci"] == "K02"
        assert row["sira"] == "BA"
        assert row["oran_B_A"] == pytest.approx(2.0)
        assert row["sus"] == 72.5
        assert row["kalibrasyon_deg"] == 2.25

    def test_rows_sorted_and_missing_condition_gives_no_ratio(self) -> None:
        rows = participant_table([_trial("K03", "A"), _trial("K01", "A"), _trial("K01", "B")])
        assert [row["katilimci"] for row in rows] == ["K01", "K03"]
        assert rows[1]["wpm_B"] is None
        assert rows[1]["oran_B_A"] is None


class TestSummary:
    def test_mean_min_max_and_faster_count(self) -> None:
        trials = [
            _trial("K01", "A", seconds=40.0),
            _trial("K01", "B", seconds=20.0),
            _trial("K02", "A", seconds=20.0),
            _trial("K02", "B", seconds=40.0),
            _trial("K03", "A", seconds=30.0),
        ]
        rows = participant_table(trials)
        summary = {line["olcu"]: line for line in condition_summary(rows)}

        wpm = summary["WPM (atlananlar hariç)"]
        slow, fast = words_per_minute(TARGET, 40.0), words_per_minute(TARGET, 20.0)
        assert wpm["min_B"] == pytest.approx(round(slow, 2))
        assert wpm["max_B"] == pytest.approx(round(fast, 2))
        # K03'ün B'si yok: B/A karşılaştırmasına girmez.
        assert faster_with_b(rows) == (1, 2)


class TestEndToEnd:
    def test_from_session_files(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        target_a, target_b = "Ellerim çok soğuk.", "Gözlüğümü bulamıyorum."
        events = [
            *_trial_events(
                0,
                0,
                "A",
                target_a,
                start=1.0,
                selections=["group:1", "letter:e"],
                seconds=40.0,
                spoken=[(target_a, None)],
            ),
            *_trial_events(
                0,
                1,
                "A",
                target_a,
                start=60.0,
                selections=["group:1"],
                seconds=180.0,
                spoken=[],
                outcome="skipped",
            ),
            *_trial_events(
                1,
                0,
                "B",
                target_b,
                start=300.0,
                selections=["group:1", "letter:g", "action:expand", "candidate:0"],
                seconds=20.0,
                spoken=[(target_b, 0)],
            ),
        ]
        _write_session(tmp_path, "K01", "20261203-100000_a.jsonl", events)
        _write_session(tmp_path, "P01", "20261201-090000_p.jsonl", events)

        trials, infos = load_study(tmp_path)
        (row,) = participant_table(trials, infos)
        assert row["katilimci"] == "K01"  # P kodlu prova analize girmez
        assert row["atlanan_A"] == 1 and row["cumle_A"] == 1
        assert row["wpm180_A"] is not None and row["wpm_A"] is not None
        assert row["wpm180_A"] < row["wpm_A"]  # type: ignore[operator]

        out = tmp_path / "analiz"
        main(["--sessions", str(tmp_path), "--out", str(out)])
        assert (out / "katilimci_tablosu.csv").exists()
        assert (out / "kosul_ozeti.csv").exists()
        assert "B'de daha hızlı: 1/1" in capsys.readouterr().out

    def test_no_sessions(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        main(["--sessions", str(tmp_path)])
        assert "K kodlu kayıt yok" in capsys.readouterr().out
