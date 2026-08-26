"""
Probability Calibration Module
Uses isotonic regression to calibrate classifier probabilities
"""

import numpy as np
import pandas as pd
from sklearn.calibration import IsotonicRegression, CalibratedClassifierCV
from sklearn.model_selection import train_test_split
import joblib
from typing import Dict, Tuple, Optional


class ProbabilityCalibrator:
    """
    Calibrates classifier probabilities using isotonic regression.
    This ensures that predicted probabilities reflect true likelihoods.
    """

    def __init__(self, method: str = "isotonic", random_state: int = 42):
        """
        Initialize calibrator
        
        Args:
            method: "isotonic" or "sigmoid"
            random_state: Random seed for reproducibility
        """
        self.method = method
        self.random_state = random_state
        self.calibrator = None
        self.is_fitted = False

    def fit(self, y_true: np.ndarray, y_prob: np.ndarray) -> Dict:
        """
        Fit calibration model
        
        Args:
            y_true: True labels
            y_prob: Predicted probabilities (for positive class)
            
        Returns:
            Calibration metrics
        """
        if self.method == "isotonic":
            self.calibrator = IsotonicRegression(out_of_bounds='clip')
        else:
            self.calibrator = CalibratedClassifierCV(method='sigmoid', cv='prefit')

        # Fit calibrator
        if self.method == "isotonic":
            self.calibrator.fit(y_prob, y_true)
        else:
            # For sigmoid, we need the underlying classifier
            raise NotImplementedError("Sigmoid calibration requires the classifier object")

        self.is_fitted = True

        # Calculate calibration metrics
        calibrated_probs = self.calibrator.predict(y_prob)
        metrics = self._calculate_calibration_metrics(y_true, y_prob, calibrated_probs)

        return metrics

    def predict_proba(self, y_prob: np.ndarray) -> np.ndarray:
        """
        Calibrate probabilities
        
        Args:
            y_prob: Uncalibrated probabilities
            
        Returns:
            Calibrated probabilities
        """
        if not self.is_fitted:
            raise ValueError("Calibrator not fitted. Call fit() first.")

        return self.calibrator.predict(y_prob)

    def _calculate_calibration_metrics(self, y_true: np.ndarray, 
                                     y_prob_uncalibrated: np.ndarray,
                                     y_prob_calibrated: np.ndarray) -> Dict:
        """
        Calculate calibration metrics
        """
        # Expected Calibration Error (ECE)
        ece_uncalibrated = self._calculate_ece(y_true, y_prob_uncalibrated)
        ece_calibrated = self._calculate_ece(y_true, y_prob_calibrated)

        # Brier score (lower is better)
        brier_uncalibrated = np.mean((y_true - y_prob_uncalibrated) ** 2)
        brier_calibrated = np.mean((y_true - y_prob_calibrated) ** 2)

        return {
            'ece_uncalibrated': ece_uncalibrated,
            'ece_calibrated': ece_calibrated,
            'ece_improvement': ece_uncalibrated - ece_calibrated,
            'brier_uncalibrated': brier_uncalibrated,
            'brier_calibrated': brier_calibrated,
            'brier_improvement': brier_uncalibrated - brier_calibrated
        }

    def _calculate_ece(self, y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
        """
        Calculate Expected Calibration Error
        """
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        bin_lowers = bin_boundaries[:-1]
        bin_uppers = bin_boundaries[1:]

        ece = 0.0
        for bin_lower, bin_upper in zip(bin_lowers, bin_uppers):
            # Mask for samples in this bin
            in_bin = (y_prob > bin_lower) & (y_prob <= bin_upper)
            prop_in_bin = in_bin.mean()

            if prop_in_bin > 0:
                # Average accuracy and confidence in this bin
                accuracy_in_bin = y_true[in_bin].mean()
                avg_confidence_in_bin = y_prob[in_bin].mean()
                ece += prop_in_bin * np.abs(accuracy_in_bin - avg_confidence_in_bin)

        return ece



    def save_calibrator(self, path: str):
        """Save fitted calibrator"""
        if not self.is_fitted:
            raise ValueError("Cannot save unfitted calibrator")

        joblib.dump({
            'calibrator': self.calibrator,
            'method': self.method,
            'random_state': self.random_state,
            'is_fitted': self.is_fitted
        }, path)
        print(f"Calibrator saved to {path}")

    def load_calibrator(self, path: str):
        """Load fitted calibrator"""
        data = joblib.load(path)
        self.calibrator = data['calibrator']
        self.method = data['method']
        self.random_state = data['random_state']
        self.is_fitted = data['is_fitted']
        print(f"Calibrator loaded from {path}")


if __name__ == "__main__":
    # Example usage
    print("Probability Calibration Module")
    print("This module provides isotonic regression calibration for classifier probabilities.")
    print("Use this to ensure predicted probabilities reflect true likelihoods.")
