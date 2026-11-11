"""Tests for app.models.calibration.ProbabilityCalibrator."""

import numpy as np
import pytest

from app.models.calibration import ProbabilityCalibrator


@pytest.fixture
def calibrator():
    return ProbabilityCalibrator()


class TestExpectedCalibrationError:
    def test_perfectly_calibrated_extremes_is_zero(self, calibrator):
        y = np.array([0, 0, 1, 1])
        p = np.array([0.0, 0.0, 1.0, 1.0])
        assert calibrator._calculate_ece(y, p) == pytest.approx(0.0)

    def test_zero_probabilities_are_counted(self, calibrator):
        # Predicting 0.0 for samples that are half positive is off by 0.5.
        y = np.array([0, 1, 0, 1])
        p = np.zeros(4)
        assert calibrator._calculate_ece(y, p) == pytest.approx(0.5)

    def test_mixed_bins_weighted_by_bin_size(self, calibrator):
        # Bin [0, 0.1]: p=0.0, all negative -> gap 0, weight 0.5
        # Bin (0.7, 0.8]: p=0.8, 1 of 2 positive -> gap 0.3, weight 0.5
        y = np.array([0, 0, 1, 0])
        p = np.array([0.0, 0.0, 0.8, 0.8])
        assert calibrator._calculate_ece(y, p) == pytest.approx(0.15)

    def test_accepts_python_lists(self, calibrator):
        assert calibrator._calculate_ece([0, 1], [0.0, 0.0]) == pytest.approx(0.5)


class TestFitAndPredict:
    def test_predict_before_fit_raises(self, calibrator):
        with pytest.raises(ValueError):
            calibrator.predict_proba(np.array([0.5]))

    def test_fit_returns_metrics_and_improves_miscalibrated_scores(self, calibrator):
        rng = np.random.default_rng(0)
        true_p = rng.uniform(0, 1, 2000)
        y = (rng.uniform(0, 1, 2000) < true_p).astype(int)
        overconfident = np.clip(true_p ** 3, 0, 1)

        metrics = calibrator.fit(y, overconfident)

        assert calibrator.is_fitted
        assert set(metrics) == {
            "ece_uncalibrated", "ece_calibrated", "ece_improvement",
            "brier_uncalibrated", "brier_calibrated", "brier_improvement",
        }
        assert metrics["ece_calibrated"] < metrics["ece_uncalibrated"]
        out = calibrator.predict_proba(overconfident)
        assert out.min() >= 0.0 and out.max() <= 1.0

    def test_sigmoid_method_not_implemented(self):
        with pytest.raises(NotImplementedError):
            ProbabilityCalibrator(method="sigmoid").fit(np.array([0, 1]), np.array([0.2, 0.8]))

    def test_save_unfitted_raises(self, calibrator, tmp_path):
        with pytest.raises(ValueError):
            calibrator.save_calibrator(str(tmp_path / "cal.joblib"))

    def test_save_load_roundtrip(self, calibrator, tmp_path):
        y = np.array([0, 0, 1, 1, 1, 0])
        p = np.array([0.1, 0.3, 0.6, 0.9, 0.7, 0.4])
        calibrator.fit(y, p)
        path = tmp_path / "cal.joblib"
        calibrator.save_calibrator(str(path))

        loaded = ProbabilityCalibrator()
        loaded.load_calibrator(str(path))
        assert loaded.is_fitted
        np.testing.assert_allclose(loaded.predict_proba(p), calibrator.predict_proba(p))
