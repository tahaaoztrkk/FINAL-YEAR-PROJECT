"""Öznitelik çıkarma, kalibrasyon ve yumuşatma testleri."""

from __future__ import annotations

import numpy as np
import pytest

from gaze_aac.gaze.calibration import CalibrationError, GazeMapper, pixels_to_degrees
from gaze_aac.gaze.features import FEATURE_DIM, FEATURE_NAMES, extract_features
from gaze_aac.gaze.filters import GazeSmoother, OneEuroFilter
from gaze_aac.schemas.gaze import CalibrationSample


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


class TestGazeMapper:
    @staticmethod
    def _samples(count: int = 40) -> list[CalibrationSample]:
        """Doğrusal ilişkili sentetik kalibrasyon verisi."""
        rng = np.random.default_rng(0)
        samples: list[CalibrationSample] = []
        for _ in range(count):
            fx, fy = rng.uniform(0.0, 1.0, size=2)
            features = [fx, fy, *rng.normal(0, 0.01, size=FEATURE_DIM - 2)]
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
