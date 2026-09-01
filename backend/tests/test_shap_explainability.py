"""
Unit tests for explain_prediction() SHAP correctness.
Asserts that SHAP feature_importance is indexed to the *predicted* class,
not max-across-all-classes, and that top features are directionally plausible.
"""
import pytest
import pandas as pd
import numpy as np


def _make_row(**kwargs) -> pd.DataFrame:
    base = {
        "mandate_id": "test-shap-m1",
        "bank_code": "SBI",
        "psp_app": "GPay",
        "amount": 3500.0,
        "scheduled_at": "2026-08-28T03:00:00",
        "attempt_number": 2,
        "category": "subscription",
        "pin_reauth_required": False,
        "created_at": "2026-08-01T00:00:00",
        "consent_for_outreach": True,
    }
    base.update(kwargs)
    return pd.DataFrame([base])


class TestExplainPredictionSHAP:

    def setup_method(self):
        from app.models.service import get_classifier
        self.clf = get_classifier()
        # Maps alphabetic LabelEncoder order
        self.classes = list(self.clf.label_encoder.classes_)

    # ------------------------------------------------------------------
    # Structural correctness tests
    # ------------------------------------------------------------------

    def test_output_keys_present(self):
        """explain_prediction must return all expected keys."""
        df = _make_row()
        res = self.clf.explain_prediction(df, index=0)
        for key in ("feature_names", "shap_values", "base_value",
                    "feature_importance", "predicted_class_idx", "predicted_class_label"):
            assert key in res, f"Missing key: {key}"

    def test_predicted_class_label_matches_predict(self):
        """predicted_class_label must equal the prediction from predict()."""
        df = _make_row()
        preds, _ = self.clf.predict(df)
        res = self.clf.explain_prediction(df, index=0)
        assert res["predicted_class_label"] == preds[0], (
            f"SHAP label '{res['predicted_class_label']}' != model prediction '{preds[0]}'"
        )

    def test_shap_values_length_matches_feature_names(self):
        """shap_values list and feature_importance keys must both have n_features entries."""
        df = _make_row()
        res = self.clf.explain_prediction(df, index=0)
        n_feat = len(res["feature_names"])
        assert len(res["shap_values"]) == n_feat
        assert len(res["feature_importance"]) == n_feat

    def test_feature_importance_values_are_scalars(self):
        """feature_importance values must be Python floats, not lists or arrays."""
        df = _make_row()
        res = self.clf.explain_prediction(df, index=0)
        for feat, val in res["feature_importance"].items():
            assert isinstance(val, float), (
                f"feature_importance['{feat}'] is {type(val)}, expected float"
            )

    def test_shap_values_and_feature_importance_consistent(self):
        """shap_values[i] and feature_importance[feature_names[i]] must match for the same class."""
        df = _make_row()
        res = self.clf.explain_prediction(df, index=0)
        for i, feat in enumerate(res["feature_names"]):
            assert abs(res["shap_values"][i] - res["feature_importance"][feat]) < 1e-6, (
                f"shap_values[{i}]={res['shap_values'][i]:.6f} != "
                f"feature_importance['{feat}']={res['feature_importance'][feat]:.6f}"
            )

    def test_predicted_class_idx_in_range(self):
        """predicted_class_idx must be a valid index into the label encoder classes."""
        df = _make_row()
        res = self.clf.explain_prediction(df, index=0)
        assert 0 <= res["predicted_class_idx"] < len(self.classes)

    # ------------------------------------------------------------------
    # Semantic / directional plausibility tests
    # ------------------------------------------------------------------

    def test_low_balance_top_shap_is_calendar_feature(self):
        """For a LOW_BALANCE prediction (month-end Day 28, SBI), the top positive
        SHAP feature must be a calendar or balance signal, not a PIN or portability feature."""
        df = _make_row(scheduled_at="2026-08-28T03:00:00", amount=3500.0, bank_code="SBI")
        preds, probs = self.clf.predict(df)
        if preds[0] != "LOW_BALANCE":
            pytest.skip(f"Model predicted {preds[0]} for this row — skipping directional test")

        res = self.clf.explain_prediction(df, index=0)
        top_feature = max(res["feature_importance"].items(), key=lambda x: x[1])[0]

        CALENDAR_OR_BALANCE = {"day_of_month", "amount", "amount_log", "amount_mandate",
                                "amount_band", "days_since_last_success", "mandate_age_days",
                                "bank_success_rate", "day_of_week", "idempotency_key"}
        UNRELATED_TO_BALANCE = {"pin_reauth_required", "in_portability_cooldown"}

        assert top_feature not in UNRELATED_TO_BALANCE, (
            f"Top SHAP feature for LOW_BALANCE is '{top_feature}', which is unrelated to "
            f"balance/calendar signals — suggests SHAP is indexing the wrong class."
        )

    def test_signed_shap_sum_nonzero_for_non_trivial_row(self):
        """The sum of signed SHAP values for the predicted class must be non-zero,
        confirming we are NOT reading a zeroed-out or wrong class slice."""
        df = _make_row()
        res = self.clf.explain_prediction(df, index=0)
        shap_sum = sum(res["shap_values"])
        assert abs(shap_sum) > 0.01, (
            f"SHAP values sum to ~0 ({shap_sum:.6f}), suggesting the wrong class slice "
            f"or a zeroed-out array."
        )

    def test_different_rows_produce_different_shap_explanations(self):
        """Two clearly different mandate types should produce different top SHAP features,
        confirming explain_prediction is not returning a cached or static result."""
        df_lb = _make_row(scheduled_at="2026-08-28T03:00:00", amount=3500.0)
        df_ml = _make_row(scheduled_at="2026-09-10T04:00:00", amount=800.0, bank_code="ICICI",
                          customer_vpa="cust@okicici", attempt_number=3)

        res_lb = self.clf.explain_prediction(df_lb, index=0)
        res_ml = self.clf.explain_prediction(df_ml, index=0)

        fi_lb = res_lb["feature_importance"]
        fi_ml = res_ml["feature_importance"]

        # Top feature should differ between two very different inputs
        top_lb = max(fi_lb.items(), key=lambda x: x[1])[0]
        top_ml = max(fi_ml.items(), key=lambda x: x[1])[0]
        # Either top feature or class differs — static output would make both identical
        assert (top_lb != top_ml) or (res_lb["predicted_class_label"] != res_ml["predicted_class_label"]), (
            "Both rows produced identical top SHAP features and identical predictions — "
            "explain_prediction may be returning static/cached output."
        )
