"""Öznitelik çıkarma, kalibrasyon ve yumuşatma testleri."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from gaze_aac.gaze.calibration import CalibrationError, GazeMapper, pixels_to_degrees
from gaze_aac.gaze.features import FEATURE_DIM, FEATURE_NAMES, extract_features
from gaze_aac.gaze.filters import GazeSmoother, OneEuroFilter
from gaze_aac.schemas.gaze import CalibrationSample

OPEN_L = FEATURE_NAMES.index("left_eye_openness")
OPEN_R = FEATURE_NAMES.index("right_eye_openness")
YAW = FEATURE_NAMES.index("head_yaw")
PITCH = FEATURE_NAMES.index("head_pitch")


def _head_samples(
    count: int, *, head_spread: float, seed: int = 0, gain: float = 0.6
) -> list[CalibrationSample]:
    """Baş pozunun bakışı etkilediği sentetik veri.

    İris konumu, ekrandaki hedef eksi başın katkısıdır: başı sağa çeviren
    kullanıcı aynı noktaya bakmak için gözünü daha az çevirir. Model ancak baş
    özniteliklerini görürse bunu çözebilir.
    """
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(count):
        tx, ty = rng.uniform(0.05, 0.95, size=2)
        yaw, pitch = rng.uniform(-head_spread / 2, head_spread / 2, size=2)
        features = list(rng.normal(0, 0.002, size=FEATURE_DIM))
        features[0] = features[2] = tx - gain * yaw + rng.normal(0, 0.005)
        features[1] = features[3] = ty - gain * pitch + rng.normal(0, 0.005)
        features[OPEN_L] = features[OPEN_R] = 0.3 + rng.normal(0, 0.01)
        features[YAW], features[PITCH] = yaw, pitch
        samples.append(CalibrationSample(features=features, target_x=tx, target_y=ty))
    return samples


def _fake_landmarks(iris_offset: float = 0.0) -> np.ndarray:
    """Sentetik landmark dizisi.

    Gerçek MediaPipe çıktısı yerine kontrollü bir yüz kurar: iris konumu
    parametreyle kaydırılabildiği için öznitelik çıkarımının bakış yönüne
    duyarlı olduğu doğrulanabilir.
    """
    points = np.full((478, 3), 0.5, dtype=np.float64)

    points[33] = [0.30, 0.40, 0.0]  # sol göz dış köşe
    points[133] = [0.42, 0.40, 0.0]  # sol göz iç köşe
    points[159] = [0.36, 0.37, 0.0]  # sol göz üst
    points[145] = [0.36, 0.43, 0.0]  # sol göz alt
    points[263] = [0.70, 0.40, 0.0]  # sağ göz dış köşe
    points[362] = [0.58, 0.40, 0.0]  # sağ göz iç köşe
    points[386] = [0.64, 0.37, 0.0]
    points[374] = [0.64, 0.43, 0.0]
    points[234] = [0.25, 0.50, 0.0]  # yüz sol
    points[454] = [0.75, 0.50, 0.0]  # yüz sağ
    points[1] = [0.50, 0.50, 0.0]  # burun
    points[152] = [0.50, 0.75, 0.0]  # çene
    points[10] = [0.50, 0.25, 0.0]  # alın

    for index in (468, 469, 470, 471, 472):
        points[index] = [0.36 + iris_offset, 0.40, 0.0]
    for index in (473, 474, 475, 476, 477):
        points[index] = [0.64 + iris_offset, 0.40, 0.0]

    return points


class TestFeatures:
    def test_vector_length_matches_contract(self) -> None:
        features = extract_features(_fake_landmarks())
        assert len(features.values) == FEATURE_DIM == len(FEATURE_NAMES)

    def test_iris_shift_changes_horizontal_feature(self) -> None:
        center = extract_features(_fake_landmarks(0.0)).values
        shifted = extract_features(_fake_landmarks(0.03)).values
        assert center[0] != pytest.approx(shifted[0])

    def test_rejects_wrong_shape(self) -> None:
        with pytest.raises(ValueError, match="refine_landmarks"):
            extract_features(np.zeros((68, 2)))

    def test_output_is_finite(self) -> None:
        values = extract_features(_fake_landmarks()).values
        assert np.all(np.isfinite(values))


FEATURE_FIXTURE = (
    Path(__file__).resolve().parents[2] / "frontend/src/features/gaze/__fixtures__/features.json"
)


def _fixture_cases() -> list[dict[str, Any]]:
    data = json.loads(FEATURE_FIXTURE.read_text(encoding="utf-8"))
    assert data["feature_names"] == list(FEATURE_NAMES)
    return list(data["cases"])


class TestFeatureFixture:
    """TypeScript'le ortak test verisi (features.ts aynı dosyaya karşı test edilir).

    Burada kırmızı: features.py değişmiş. Bilerek değiştiyse
    ``python scripts/export_feature_fixture.py`` çalıştırılır ve features.ts de
    aynı şekilde güncellenir; yoksa tarayıcıdaki öznitelikler sunucudaki
    modelle uyuşmaz.
    """

    @pytest.mark.parametrize("case", _fixture_cases(), ids=lambda case: case["name"])
    def test_python_matches_fixture(self, case: dict[str, Any]) -> None:
        points = np.tile(np.array([0.5, 0.5, 0.0]), (478, 1))
        for index, xyz in case["points"].items():
            points[int(index)] = xyz
        result = extract_features(points)
        np.testing.assert_allclose(result.values, case["values"], rtol=0, atol=1e-12)
        assert result.confidence == pytest.approx(case["confidence"], abs=1e-12)


class TestGazeMapper:
    @staticmethod
    def _samples(count: int = 40) -> list[CalibrationSample]:
        """Doğrusal ilişkili sentetik kalibrasyon verisi."""
        rng = np.random.default_rng(0)
        samples: list[CalibrationSample] = []
        for _ in range(count):
            fx, fy = rng.uniform(0.0, 1.0, size=2)
            features = [fx, fy, *rng.normal(0, 0.01, size=FEATURE_DIM - 2)]
            # Gerçekçi göz açıklığı: kırpış filtresi açık gözleri elememeli.
            features[OPEN_L] += 0.3
            features[OPEN_R] += 0.3
            samples.append(
                CalibrationSample(
                    features=features,
                    target_x=float(np.clip(fx * 0.9 + 0.05, 0, 1)),
                    target_y=float(np.clip(fy * 0.9 + 0.05, 0, 1)),
                )
            )
        return samples

    def test_predict_before_fit_raises(self) -> None:
        with pytest.raises(CalibrationError, match="kalibrasyon"):
            GazeMapper().predict([0.0] * FEATURE_DIM)

    def test_fit_requires_enough_samples(self) -> None:
        with pytest.raises(CalibrationError, match=r"12"):
            GazeMapper().fit(self._samples(5))

    def test_fit_then_predict_in_range(self) -> None:
        mapper = GazeMapper()
        mapper.fit(self._samples())
        x, y = mapper.predict([0.5, 0.5] + [0.0] * (FEATURE_DIM - 2))
        assert 0.0 <= x <= 1.0
        assert 0.0 <= y <= 1.0

    def test_learns_the_underlying_relation(self) -> None:
        samples = self._samples(60)
        mapper = GazeMapper()
        mapper.fit(samples)

        report = mapper.evaluate(
            samples,
            screen_width_px=1920,
            screen_height_px=1080,
            screen_width_cm=34.5,
            distance_cm=60.0,
        )
        # Doğrusal ilişki öğrenilebilmeli; eşik gevşek, amaç regresyonun
        # tamamen kopuk olmadığını görmek.
        assert report.mean_error_deg < 2.0

    def test_default_is_first_degree(self) -> None:
        assert GazeMapper().degree == 1

    def test_rejects_wrong_vector_length(self) -> None:
        samples = self._samples()
        samples[0] = CalibrationSample(features=[0.5] * 8, target_x=0.5, target_y=0.5)
        with pytest.raises(CalibrationError, match="12 öznitelik"):
            GazeMapper().fit(samples)
        mapper = GazeMapper()
        mapper.fit(self._samples())
        with pytest.raises(CalibrationError, match="12 öznitelik"):
            mapper.predict([0.5] * 8)


class TestHeadPose:
    """10 Kasım ölçümündeki hata: baş sabit kalibrasyon + küçük baş hareketi."""

    def test_head_features_left_out_when_head_was_still(self) -> None:
        mapper = GazeMapper()
        mapper.fit(_head_samples(120, head_spread=0.004))
        assert not mapper.uses_head_pose
        assert "head_yaw" not in mapper.feature_names

    def test_still_head_model_does_not_fly_off_when_head_moves(self) -> None:
        mapper = GazeMapper()
        mapper.fit(_head_samples(120, head_spread=0.004))
        features = [0.5] * FEATURE_DIM
        features[OPEN_L] = features[OPEN_R] = 0.3
        features[YAW] = features[PITCH] = 0.0
        before = mapper.predict(features)
        features[YAW] = features[PITCH] = 0.05  # kalibrasyonun ~12 katı baş hareketi
        after = mapper.predict(features)
        # Baş sütunları modelde olsaydı tahmin ekranın kenarına fırlardı.
        assert abs(after[0] - before[0]) < 0.02
        assert abs(after[1] - before[1]) < 0.02
        assert not mapper.in_calibrated_pose(features) or not mapper.uses_head_pose

    def test_head_features_used_when_calibration_had_head_poses(self) -> None:
        mapper = GazeMapper()
        mapper.fit(_head_samples(200, head_spread=0.12))
        assert mapper.uses_head_pose
        assert {"head_yaw", "head_pitch"} <= set(mapper.feature_names)

    def test_head_aware_model_is_more_accurate_with_head_movement(self) -> None:
        train = _head_samples(200, head_spread=0.12, seed=1)
        test = _head_samples(60, head_spread=0.12, seed=2)
        screen = {
            "screen_width_px": 1920,
            "screen_height_px": 1080,
            "screen_width_cm": 34.5,
            "distance_cm": 60.0,
        }

        with_head = GazeMapper()
        with_head.fit(train)
        without_head = GazeMapper(head_min_spread=float("inf"))
        without_head.fit(train)

        assert not without_head.uses_head_pose
        error_with = with_head.evaluate(test, **screen).mean_error_deg
        error_without = without_head.evaluate(test, **screen).mean_error_deg
        assert error_with < error_without / 2

    def test_in_calibrated_pose(self) -> None:
        mapper = GazeMapper()
        mapper.fit(_head_samples(200, head_spread=0.12))
        inside = [0.5] * FEATURE_DIM
        inside[YAW] = inside[PITCH] = 0.0
        outside = list(inside)
        outside[YAW] = 0.5
        assert mapper.in_calibrated_pose(inside)
        assert not mapper.in_calibrated_pose(outside)
        assert mapper.in_calibrated_pose(outside, margin=1.0)


class TestBlinkFilter:
    def test_blink_samples_are_left_out(self) -> None:
        samples = _head_samples(60, head_spread=0.0)
        rng = np.random.default_rng(5)
        blinks = []
        for _ in range(10):
            features = [0.0] * FEATURE_DIM
            features[1] = features[3] = 1.5  # kapanan kapak irisi aşağı iter
            features[OPEN_L] = features[OPEN_R] = 0.03
            blinks.append(
                CalibrationSample(
                    features=features, target_x=float(rng.uniform()), target_y=float(rng.uniform())
                )
            )
        mapper = GazeMapper()
        mapper.fit(samples + blinks)
        assert mapper.discarded_blinks == 10
        assert mapper.sample_count == 60

    def test_looking_down_is_not_a_blink(self) -> None:
        # Alt sıraya bakarken göz kısılır; eşik oradan alındığı için elenmez.
        samples = _head_samples(60, head_spread=0.0)
        for sample in samples:
            if sample.target_y >= 0.85:
                sample.features[OPEN_L] = sample.features[OPEN_R] = 0.2
        mapper = GazeMapper()
        mapper.fit(samples)
        assert mapper.discarded_blinks == 0

    def test_all_blinks_is_an_error(self) -> None:
        samples = _head_samples(20, head_spread=0.0)
        for i, sample in enumerate(samples):
            sample.features[OPEN_L] = sample.features[OPEN_R] = 0.3 if i < 5 else 0.01
        with pytest.raises(CalibrationError, match="Kırpış"):
            GazeMapper().fit(samples)


class TestDegreeConversion:
    def test_zero_error_is_zero_degrees(self) -> None:
        assert pixels_to_degrees(0, 1920, 34.5, 60.0) == pytest.approx(0.0)

    def test_larger_error_is_more_degrees(self) -> None:
        small = pixels_to_degrees(20, 1920, 34.5, 60.0)
        large = pixels_to_degrees(80, 1920, 34.5, 60.0)
        assert large > small

    def test_farther_screen_means_fewer_degrees(self) -> None:
        near = pixels_to_degrees(50, 1920, 34.5, 40.0)
        far = pixels_to_degrees(50, 1920, 34.5, 90.0)
        assert far < near


class TestSmoothing:
    def test_one_euro_reduces_jitter(self) -> None:
        rng = np.random.default_rng(1)
        filt = OneEuroFilter(min_cutoff=0.5, beta=0.0)

        raw = [0.5 + rng.normal(0, 0.05) for _ in range(60)]
        smoothed = [filt(value, index / 30.0) for index, value in enumerate(raw)]

        assert np.std(smoothed[10:]) < np.std(raw[10:])

    def test_moving_average_mode(self) -> None:
        smoother = GazeSmoother(use_one_euro=False, window=3)
        smoother.smooth(0.0, 0.0, 0.0)
        smoother.smooth(1.0, 1.0, 0.1)
        x, y = smoother.smooth(2.0, 2.0, 0.2)
        assert x == pytest.approx(1.0)
        assert y == pytest.approx(1.0)

    def test_reset_clears_state(self) -> None:
        smoother = GazeSmoother()
        smoother.smooth(0.9, 0.9, 0.0)
        smoother.reset()
        x, _ = smoother.smooth(0.1, 0.1, 0.0)
        assert x == pytest.approx(0.1)
