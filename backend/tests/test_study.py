"""Kullanıcı testi: plan, oturum kaydı ve analiz.

Deney bir kez yapılır; kayıtta eksik bir alan ya da yanlış hesaplanan bir
ölçü Aralık'ta fark edilirse oturumlar tekrarlanamaz. Bu yüzden kayıttan
tabloya kadar bütün yol burada sentetik bir oturumla sınanır.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gaze_aac.config import Settings
from gaze_aac.evaluation.metrics import letter_by_letter_selections, words_per_minute
from gaze_aac.evaluation.study import (
    compare_conditions,
    extract_trials,
    load_study,
    load_survey,
    main,
    paired_comparison,
    summarize,
    sus_score,
)
from gaze_aac.main import create_app
from gaze_aac.nlp.schemes import tokenize
from gaze_aac.study.protocol import (
    StudyMaterials,
    build_plan,
    condition_order,
    normalize_participant_id,
    sentences_match,
)
from gaze_aac.study.recorder import SessionRecorder, loggable_features

REAL_MATERIALS = Settings().study_sentences_path


def _materials(tmp_path: Path, **overrides: object) -> Path:
    data = {
        "scheme": "S1",
        "practice": {"A": ["Kolay gelsin."], "B": ["İyi akşamlar."]},
        "sets": [
            ["Annemi aramak istiyorum.", "Ellerim çok soğuk."],
            ["Gözlüğümü bulamıyorum.", "Bu gece rahat uyudum."],
        ],
    }
    data.update(overrides)
    path = tmp_path / "sentences.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Plan
# --------------------------------------------------------------------------


class TestParticipantId:
    @pytest.mark.parametrize(("raw", "code"), [("k7", "K07"), (" K01 ", "K01"), ("p12", "P12")])
    def test_normalizes(self, raw: str, code: str) -> None:
        assert normalize_participant_id(raw) == code

    @pytest.mark.parametrize("raw", ["", "K", "07", "KK1", "../K01", "K01/..", "K1234"])
    def test_rejects_unsafe_or_malformed(self, raw: str) -> None:
        # Kod klasör adı oluyor; yol karakteri geçmemeli.
        with pytest.raises(ValueError):
            normalize_participant_id(raw)

    def test_order_alternates(self) -> None:
        assert condition_order("K01") == ("A", "B")
        assert condition_order("K02") == ("B", "A")
        assert condition_order("k13") == ("A", "B")


class TestPlan:
    def test_practice_first_then_set_by_block_position(self, tmp_path: Path) -> None:
        materials = StudyMaterials.load(_materials(tmp_path))

        first, second = build_plan("K02", materials)

        assert (first.condition, second.condition) == ("B", "A")
        assert [t.text for t in first.trials] == [
            "İyi akşamlar.",
            "Annemi aramak istiyorum.",
            "Ellerim çok soğuk.",
        ]
        assert [t.practice for t in first.trials] == [True, False, False]
        # İkinci blok hep ikinci seti alır, koşul ne olursa olsun.
        assert [t.text for t in second.trials if not t.practice] == list(materials.sets[1])
        assert [t.index for t in second.trials] == [0, 1, 2]

    def test_each_condition_sees_each_set_across_participants(self, tmp_path: Path) -> None:
        materials = StudyMaterials.load(_materials(tmp_path))
        a_sets = set()
        for code in ("K01", "K02"):
            for block in build_plan(code, materials):
                if block.condition == "A":
                    a_sets.add(tuple(t.text for t in block.trials if not t.practice))
        assert a_sets == set(materials.sets)

    def test_rejects_unequal_sets(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="eşit"):
            StudyMaterials.load(_materials(tmp_path, sets=[["Ellerim çok soğuk."], []]))

    def test_rejects_duplicate_sentence(self, tmp_path: Path) -> None:
        path = _materials(tmp_path, sets=[["Ellerim çok soğuk."], ["ellerim çok soğuk"]])
        with pytest.raises(ValueError, match="iki kez"):
            StudyMaterials.load(path)

    def test_rejects_unknown_scheme(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="S9"):
            StudyMaterials.load(_materials(tmp_path, scheme="S9"))


class TestRealMaterials:
    def test_loads_with_two_balanced_sets(self) -> None:
        materials = StudyMaterials.load(REAL_MATERIALS)
        first, second = materials.sets
        assert len(first) == len(second) == 10
        assert materials.practice["A"] and materials.practice["B"]
        letters = [sum(len(w) for s in group for w in tokenize(s)) for group in (first, second)]
        assert abs(letters[0] - letters[1]) <= 10

    def test_no_study_sentence_is_in_the_corpus(self) -> None:
        """Model test cümlesini eğitimde görürse B koşulu ezber ölçer."""
        corpus = Settings().source_corpus_path
        seen = set()
        with corpus.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    seen.add(" ".join(tokenize(json.loads(line)["text"])))
        materials = StudyMaterials.load(REAL_MATERIALS)
        leaked = [s for s in materials.all_sentences() if " ".join(tokenize(s)) in seen]
        assert leaked == []


class TestMatch:
    def test_ignores_case_and_punctuation(self) -> None:
        assert sentences_match(
            "bugün biraz erken yatmak istiyorum", "Bugün biraz erken yatmak istiyorum."
        )
        assert sentences_match("İYİ AKŞAMLAR", "iyi akşamlar")

    def test_turkish_dotted_i_matters(self) -> None:
        assert not sentences_match("ıyı akşamlar", "İyi akşamlar.")

    def test_empty_never_matches(self) -> None:
        assert not sentences_match("", "")


# --------------------------------------------------------------------------
# Kayıt
# --------------------------------------------------------------------------


class TestRecorder:
    def test_lines_are_on_disk_before_close(self, tmp_path: Path) -> None:
        ticks = iter([10.0, 10.5, 12.25])
        recorder = SessionRecorder(tmp_path / "K01" / "a.jsonl", clock=lambda: next(ticks))

        recorder.record("trial_start", target="Su istiyorum.")
        recorder.record("speak", text="Su istiyorum.")

        lines = (tmp_path / "K01" / "a.jsonl").read_text(encoding="utf-8").splitlines()
        assert [json.loads(line) for line in lines] == [
            {"t": 0.5, "event": "trial_start", "target": "Su istiyorum."},
            {"t": 2.25, "event": "speak", "text": "Su istiyorum."},
        ]
        recorder.close()
        recorder.record("lost")
        assert len((tmp_path / "K01" / "a.jsonl").read_text(encoding="utf-8").splitlines()) == 2

    def test_path_layout(self, tmp_path: Path) -> None:
        from datetime import datetime

        recorder = SessionRecorder.create(
            tmp_path, "K03", "abc123", now=datetime(2026, 12, 3, 14, 5, 9)
        )
        assert recorder.path == tmp_path / "K03" / "20261203-140509_abc123.jsonl"
        recorder.close()

    def test_face_mesh_is_never_written(self) -> None:
        assert loggable_features([0.123456789] * 12) == [0.12346] * 12
        assert loggable_features([0.0] * 478 * 3) is None


class TestWebSocketRecording:
    @pytest.fixture
    def data_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        (tmp_path / "study").mkdir()
        shutil.copy(REAL_MATERIALS, tmp_path / "study" / "sentences.json")
        return tmp_path

    @pytest.fixture
    def client(self, data_dir: Path) -> TestClient:
        with TestClient(create_app()) as test_client:
            yield test_client

    @staticmethod
    def _events(data_dir: Path, participant: str) -> list[dict[str, object]]:
        files = sorted((data_dir / "sessions" / participant).glob("*.jsonl"))
        assert len(files) == 1
        return [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]

    def test_full_trial_is_recorded(self, client: TestClient, data_dir: Path) -> None:
        with client.websocket_connect("/ws") as socket:
            socket.receive_json()  # ready
            socket.send_json({"type": "hello", "screen_width": 1920, "screen_height": 1080})
            socket.send_json({"type": "study_start", "participant_id": "k3"})
            plan = socket.receive_json()
            assert plan["type"] == "study_plan"
            assert (plan["participant_id"], plan["order"]) == ("K03", "AB")
            assert plan["blocks"][1]["trials"][0]["practice"] is True

            socket.send_json({"type": "trial_start", "block_index": 1, "trial_index": 2})
            for target_id in ("group:5", "letter:s", "action:space", "action:expand"):
                socket.send_json({"type": "select", "target_id": target_id})
                assert socket.receive_json()["type"] == "selection"
            socket.send_json({"type": "expand", "abbreviation": "s i", "scheme": "S1"})
            candidates = socket.receive_json()
            assert candidates["candidates"][0]["text"] == "Su istiyorum."
            socket.send_json({"type": "speak", "text": "Su istiyorum."})
            socket.send_json(
                {
                    "type": "trial_end",
                    "block_index": 1,
                    "trial_index": 2,
                    "outcome": "skipped",
                    "output": "Su istiyorum.",
                }
            )
            socket.send_json({"type": "study_end"})

        events = self._events(data_dir, "K03")
        kinds = [event["event"] for event in events]
        assert kinds == [
            "study_start",
            "trial_start",
            "selection",
            "selection",
            "selection",
            "selection",
            "expand",
            "speak",
            "trial_end",
            "study_end",
        ]
        start = events[0]
        assert start["provider"] == "mock"
        assert start["screen"] == [1920, 1080]
        assert len(str(start["materials"])) == 12

        trial_start = events[1]
        assert trial_start["condition"] == "B"
        assert trial_start["target"] == plan["blocks"][1]["trials"][2]["text"]
        assert events[2]["via"] == "click"
        assert events[6]["candidates"][0]["valid"] is True
        # Söylenen cümlenin aday sırası sunucuda bulunur.
        assert events[7]["candidate_rank"] == 0
        assert events[8]["correct"] is False
        times = [float(event["t"]) for event in events]
        assert times == sorted(times)

    def test_free_use_writes_nothing(self, client: TestClient, data_dir: Path) -> None:
        with client.websocket_connect("/ws") as socket:
            socket.receive_json()
            socket.send_json({"type": "speak", "text": "Su istiyorum."})
            socket.send_json({"type": "select", "target_id": "group:0"})
            socket.receive_json()
        assert not (data_dir / "sessions").exists()

    def test_errors_keep_connection(self, client: TestClient, data_dir: Path) -> None:
        with client.websocket_connect("/ws") as socket:
            socket.receive_json()
            socket.send_json({"type": "trial_start", "block_index": 0, "trial_index": 0})
            assert socket.receive_json()["code"] == "study_not_started"

            socket.send_json({"type": "study_start", "participant_id": "../x"})
            assert socket.receive_json()["code"] == "invalid_participant"

            socket.send_json({"type": "study_start", "participant_id": "K02"})
            assert socket.receive_json()["order"] == "BA"
            socket.send_json({"type": "trial_start", "block_index": 2, "trial_index": 0})
            assert socket.receive_json()["code"] == "unknown_trial"

    def test_disconnect_and_landmarks_are_recorded_safely(
        self, client: TestClient, data_dir: Path
    ) -> None:
        with client.websocket_connect("/ws") as socket:
            socket.receive_json()
            socket.send_json({"type": "study_start", "participant_id": "K05"})
            socket.receive_json()
            socket.send_json(
                {
                    "type": "calibration_sample",
                    "target_x": 0.5,
                    "target_y": 0.5,
                    "features": [0.1] * 1434,
                }
            )
            socket.send_json(
                {"type": "gaze", "point": {"x": 0.25, "y": 0.75, "t": 1.0, "confidence": 1.0}}
            )
            socket.receive_json()

        events = self._events(data_dir, "K05")
        sample = next(event for event in events if event["event"] == "calibration_sample")
        assert sample["features"] is None
        assert sample["feature_count"] == 1434
        gaze = next(event for event in events if event["event"] == "gaze")
        assert (gaze["x"], gaze["y"]) == (0.25, 0.75)
        assert events[-1]["event"] == "disconnect"

    def test_missing_materials(self, client: TestClient, data_dir: Path) -> None:
        (data_dir / "study" / "sentences.json").unlink()
        with client.websocket_connect("/ws") as socket:
            socket.receive_json()
            socket.send_json({"type": "study_start", "participant_id": "K01"})
            assert socket.receive_json()["code"] == "study_materials_missing"


# --------------------------------------------------------------------------
# Analiz
# --------------------------------------------------------------------------


def _trial_events(
    block: int,
    trial: int,
    condition: str,
    target: str,
    *,
    start: float,
    selections: list[str],
    seconds: float,
    spoken: list[tuple[str, int | None]],
    practice: bool = False,
    outcome: str = "done",
) -> list[dict[str, object]]:
    """Bir cümlenin kayıt satırları: hedefi okuma, seçimler, seslendirme."""
    events: list[dict[str, object]] = [
        {
            "t": start,
            "event": "trial_start",
            "block_index": block,
            "trial_index": trial,
            "condition": condition,
            "scheme": "S1",
            "target": target,
            "practice": practice,
        }
    ]
    first = start + 3.0  # hedefi okuma süresi; ölçüme girmemeli
    step = seconds / max(len(selections), 1)
    for index, target_id in enumerate(selections):
        events.append(
            {
                "t": first + index * step,
                "event": "selection",
                "target_id": target_id,
                "via": "dwell",
            }
        )
        if target_id == "action:expand":
            events.append({"t": first + index * step, "event": "expand", "candidates": []})
    for text, rank in spoken:
        events.append(
            {"t": first + seconds, "event": "speak", "text": text, "candidate_rank": rank}
        )
    events.append(
        {
            "t": first + seconds,
            "event": "trial_end",
            "block_index": block,
            "trial_index": trial,
            "outcome": outcome,
            "output": spoken[-1][0] if spoken else "",
            "target": target,
            "correct": outcome == "done",
            "practice": practice,
        }
    )
    return events


class TestMetrics:
    def test_letter_by_letter_cost(self) -> None:
        # "su istiyorum": 2 + 9 harf -> 22 seçim, 1 boşluk, 1 seslendir.
        assert letter_by_letter_selections("Su istiyorum.") == 24
        assert letter_by_letter_selections("...") == 0

    def test_words_per_minute(self) -> None:
        # "su istiyorum" 12 karakter: 11 / 10 s x 60 / 5 = 13.2
        assert words_per_minute("Su istiyorum.", 10.0) == pytest.approx(13.2)
        assert words_per_minute("Su istiyorum.", 0.0) == 0.0


class TestExtract:
    def test_measures_one_trial(self) -> None:
        events = _trial_events(
            0,
            2,
            "B",
            "Su istiyorum.",
            start=5.0,
            selections=[
                "group:5",
                "letter:s",
                "action:delete",
                "group:5",
                "letter:s",
                "action:space",
                "group:2",
                "letter:i",
                "action:expand",
                "candidate:1",
            ],
            seconds=20.0,
            spoken=[("Su içiyorum.", None), ("Su istiyorum.", 1)],
        )

        (trial,), _ = extract_trials(events, "K01")

        assert trial.counted
        assert trial.duration_s == pytest.approx(20.0)
        assert (trial.selections, trial.deletes, trial.backs) == (10, 1, 0)
        assert trial.wrong_outputs == 1
        assert trial.expands == 1
        assert trial.candidate_rank == 1
        assert trial.ksr == pytest.approx((1 - 10 / 24) * 100)
        assert trial.as_row()["aday_sirasi"] == 2

    def test_unfinished_trial_is_dropped(self) -> None:
        events = _trial_events(
            0, 0, "A", "Su istiyorum.", start=0.0, selections=["group:5"], seconds=2.0, spoken=[]
        )[:-1]
        events.append({"t": 9.0, "event": "disconnect"})
        assert extract_trials(events, "K01")[0] == []

    def test_practice_and_skipped_are_not_counted(self) -> None:
        events = [
            *_trial_events(
                0,
                0,
                "A",
                "Kolay gelsin.",
                start=0.0,
                selections=["group:3"],
                seconds=4.0,
                spoken=[("Kolay gelsin.", None)],
                practice=True,
            ),
            *_trial_events(
                0,
                1,
                "A",
                "Ellerim çok soğuk.",
                start=10.0,
                selections=["group:1"],
                seconds=4.0,
                spoken=[],
                outcome="skipped",
            ),
        ]
        trials, _ = extract_trials(events, "K01")
        assert [trial.counted for trial in trials] == [False, False]
        assert all(trial.wpm is None and trial.ksr is None for trial in trials)


def _write_session(
    root: Path, participant: str, name: str, events: list[dict[str, object]], order: str = "AB"
) -> None:
    folder = root / participant
    folder.mkdir(parents=True, exist_ok=True)
    header = {
        "t": 0.0,
        "event": "study_start",
        "participant_id": participant,
        "order": order,
        "provider": "hf_local+lora",
        "scheme": "S1",
        "materials": "abc",
    }
    lines = [json.dumps(event, ensure_ascii=False) for event in [header, *events]]
    (folder / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _participant(seconds_a: float, seconds_b: float) -> list[dict[str, object]]:
    target_a, target_b = "Ellerim çok soğuk.", "Gözlüğümü bulamıyorum."
    a_selections = ["group:1", "letter:e"] * 15 + ["action:speak"]
    b_selections = [
        "group:1",
        "letter:g",
        "action:space",
        "group:0",
        "letter:b",
        "action:expand",
        "candidate:0",
    ]
    return [
        *_trial_events(
            0,
            0,
            "A",
            target_a,
            start=1.0,
            selections=a_selections,
            seconds=seconds_a,
            spoken=[(target_a, None)],
        ),
        *_trial_events(
            1,
            0,
            "B",
            target_b,
            start=200.0,
            selections=b_selections,
            seconds=seconds_b,
            spoken=[(target_b, 0)],
        ),
    ]


class TestStudyAnalysis:
    def test_reconnect_keeps_last_attempt_and_prefix_filters_pilots(self, tmp_path: Path) -> None:
        target = "Ellerim çok soğuk."
        first = _trial_events(
            0,
            0,
            "A",
            target,
            start=1.0,
            selections=["group:1"] * 4,
            seconds=30.0,
            spoken=[(target, None)],
        )
        second = _trial_events(
            0,
            0,
            "A",
            target,
            start=1.0,
            selections=["group:1"] * 4,
            seconds=12.0,
            spoken=[(target, None)],
        )
        _write_session(tmp_path, "K01", "20261203-100000_a.jsonl", first)
        _write_session(tmp_path, "K01", "20261203-100500_b.jsonl", second)
        _write_session(tmp_path, "P01", "20261201-090000_c.jsonl", first)
        (tmp_path / "K01" / "20261203-100500_b.jsonl").open("a").write('{"t": 99, "eve')

        trials, infos = load_study(tmp_path)

        assert [trial.participant for trial in trials] == ["K01"]
        assert trials[0].duration_s == pytest.approx(12.0)
        assert len(infos) == 2

    def test_paired_comparison_on_synthetic_group(self, tmp_path: Path) -> None:
        for index, (seconds_a, seconds_b) in enumerate(
            [(60, 20), (75, 22), (50, 25), (90, 18), (66, 30), (58, 21)], start=1
        ):
            order = "AB" if index % 2 else "BA"
            _write_session(
                tmp_path, f"K{index:02d}", "s.jsonl", _participant(seconds_a, seconds_b), order
            )

        trials, infos = load_study(tmp_path)
        summaries = summarize(trials, infos)
        tests = {test.measure: test for test in compare_conditions(summaries)}

        wpm = tests["wpm"]
        assert wpm.n == 6
        assert wpm.mean_b > wpm.mean_a
        assert wpm.test in {"t", "wilcoxon"}
        assert wpm.p is not None and wpm.p < 0.05
        assert wpm.cohen_dz is not None and wpm.cohen_dz > 0
        # Seçim sayısı herkeste aynı: fark sabit, normallik sınanamaz.
        assert tests["secim"].shapiro_p is None
        b_rows = [s for s in summaries if s.condition == "B"]
        assert all(s.top1 == 100.0 for s in b_rows)

    def test_too_few_participants_gives_no_test(self) -> None:
        result = paired_comparison("wpm", [5.0], [5.0])
        assert (result.test, result.p) == ("-", None)

    def test_main_writes_tables(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        for index in range(1, 5):
            _write_session(
                tmp_path, f"K{index:02d}", "s.jsonl", _participant(60 + index, 20 + index)
            )
        survey = tmp_path / "anket.csv"
        header = ",".join(["katilimci", *(f"sus{i}" for i in range(1, 11)), "k1"])
        survey.write_text(
            f"{header}\nK01,5,1,5,1,5,1,5,1,5,1,4\nK02,3,3,3,3,3,3,3,3,3,3,\n", encoding="utf-8"
        )

        main(["--sessions", str(tmp_path)])

        out = tmp_path / "analiz"
        for name in ("cumleler.csv", "katilimci_kosul.csv", "karsilastirma.csv", "anket_ozet.csv"):
            assert (out / name).exists(), name
        printed = capsys.readouterr().out
        assert "4 katılımcı" in printed
        assert "SUS: ort 75.0" in printed

    def test_main_explains_empty_folder(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit, match="Kayıt bulunamadı"):
            main(["--sessions", str(tmp_path)])


class TestSurvey:
    def test_sus_bounds(self) -> None:
        assert sus_score([5, 1] * 5) == 100.0
        assert sus_score([1, 5] * 5) == 0.0
        assert sus_score([3] * 10) == 50.0

    def test_sus_rejects_bad_answers(self) -> None:
        with pytest.raises(ValueError):
            sus_score([3] * 9)
        with pytest.raises(ValueError):
            sus_score([0] * 10)

    def test_incomplete_sus_row_is_kept_without_score(self, tmp_path: Path) -> None:
        path = tmp_path / "anket.csv"
        header = ",".join(["katilimci", *(f"sus{i}" for i in range(1, 11)), "k1", "k2"])
        path.write_text(f"{header}\nk01,3,3,3,3,3,3,3,3,3,,4,5\n", encoding="utf-8")
        (row,) = load_survey(path)
        assert (row.participant, row.sus, row.extra) == ("K01", None, {"k1": 4, "k2": 5})
