"""
Evaluation Harness for Reclaim
Runs ablation studies using the trained classifier and recovery simulator.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import train_test_split

# Add paths for imports when run from notebooks/
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "data"))

from app.evaluation.simulator import run_configuration
from app.models.classifier import FailureClassifier
from app.models.service import MODEL_PATH
from synthetic_generation import SyntheticDataGenerator


class EvaluationHarness:
    """Runs measured ablation studies on synthetic data with the real classifier."""

    ABLATION_CONFIGS = [
        "full_system",
        "no_classifier",
        "no_smart_retry",
        "no_nudge",
        "baseline",
    ]

    def __init__(self, random_seed: int = 42):
        self.random_seed = random_seed
        self.rng = np.random.RandomState(random_seed)

    def _build_dataset(self) -> pd.DataFrame:
        generator = SyntheticDataGenerator(num_mandates=500)
        mandates_df, attempts_df, failure_events_df = generator.generate_full_dataset()
        mandate_cols = mandates_df.rename(columns={"category": "mandate_category"})
        failed = attempts_df[attempts_df["status"] == "FAILED"].copy()
        failed = failed.rename(columns={"id": "debit_attempt_id"})
        merged = failed.merge(mandate_cols, left_on="mandate_id", right_on="id", suffixes=("", "_m"))
        merged = merged.merge(
            failure_events_df[["debit_attempt_id", "category"]],
            on="debit_attempt_id",
        )
        return merged

    def train_classifier(self, data: pd.DataFrame) -> FailureClassifier:
        classifier = FailureClassifier(model_type="xgboost", random_state=self.random_seed)
        classifier.train(data, target_column="category", test_size=0.2)
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        classifier.save_model(str(MODEL_PATH))
        return classifier

    def measure_classification(self, classifier: FailureClassifier, test_data: pd.DataFrame) -> dict:
        preds, _ = classifier.predict(test_data)
        y_true = test_data["category"].astype(str).values
        y_pred = np.array([str(p) for p in preds])
        return {
            "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
            "f1_weighted": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
            "classification_report": classification_report(
                y_true, y_pred, output_dict=True, zero_division=0
            ),
        }

    def run_ablation_study(self, data: pd.DataFrame, classifier: FailureClassifier, n_runs: int = 5) -> dict:
        results = {}
        for config in self.ABLATION_CONFIGS:
            run_results = []
            for run in range(n_runs):
                _, test_data = train_test_split(
                    data,
                    test_size=0.2,
                    random_state=self.random_seed + run,
                    stratify=data["category"],
                )
                run_results.append(run_configuration(test_data, config, classifier=classifier))
            results[config] = self._calculate_statistics(run_results)
        return results

    def _calculate_statistics(self, results: list) -> dict:
        metrics = ["recovery_rate", "recovered", "revenue_recovered", "false_nudge_rate"]
        stats = {}
        for metric in metrics:
            values = [r[metric] for r in results]
            mean = float(np.mean(values))
            std = float(np.std(values))
            ci = 1.96 * std / np.sqrt(len(values)) if len(values) > 1 else 0.0
            stats[metric] = {
                "mean": mean,
                "std": std,
                "ci_lower": mean - ci,
                "ci_upper": mean + ci,
                "values": values,
            }
        return stats

    def generate_evaluation_report(self, ablation_results: dict, classification_metrics: dict) -> str:
        lines = [
            "# Reclaim Evaluation Report",
            "",
            "> **Methodology:** Measured on 500 synthetic mandates. Recovery simulation uses the trained",
            "> XGBoost classifier, NPCI compliance engine, and category-specific recovery rates.",
            "> Confidence intervals from 5 seeded train/test splits.",
            "",
            "## Classification Performance",
            "",
            f"- **F1 Macro:** {classification_metrics['f1_macro']:.3f}",
            f"- **F1 Weighted:** {classification_metrics['f1_weighted']:.3f}",
            "",
            "## Ablation Study Results",
            "",
            "| Configuration | Recovery Rate | Revenue Recovered (₹) | False Nudge Rate |",
            "|---|---|---|---|",
        ]
        for config, stats in ablation_results.items():
            rr = stats["recovery_rate"]["mean"]
            rr_ci = stats["recovery_rate"]["ci_upper"] - rr
            rev = stats["revenue_recovered"]["mean"]
            rev_ci = stats["revenue_recovered"]["ci_upper"] - rev
            fn = stats["false_nudge_rate"]["mean"]
            lines.append(
                f"| {config} | {rr:.1%} (±{rr_ci:.1%}) | ₹{rev:,.0f} (±{rev_ci:,.0f}) | {fn:.1%} |"
            )

        full = ablation_results["full_system"]["recovery_rate"]["mean"]
        base = ablation_results["baseline"]["recovery_rate"]["mean"]
        lines += [
            "",
            "## Component Impact Analysis",
            "",
            f"- **Recovery Rate Lift vs Baseline:** +{(full - base):.1%}",
            f"- **ML Classifier Contribution:** +{(full - ablation_results['no_classifier']['recovery_rate']['mean']):.1%}",
            f"- **Smart Retry Contribution:** +{(full - ablation_results['no_smart_retry']['recovery_rate']['mean']):.1%}",
            f"- **Customer Nudge Contribution:** +{(full - ablation_results['no_nudge']['recovery_rate']['mean']):.1%}",
            "",
            "## Data Limitations",
            "",
            "- Evaluation on synthetic data grounded in NPCI/RBI rules",
            "- Recovery outcomes simulated with category-specific rates (deterministic, seeded)",
            "- Real-world performance will vary with production merchant data",
        ]
        return "\n".join(lines)

    def save_results(self, ablation_results: dict, report: str, output_dir: str = "docs"):
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        with open(output_path / "ablation_results.json", "w") as f:
            json.dump(ablation_results, f, indent=2, default=str)
        with open(output_path / "evaluation_report.md", "w") as f:
            f.write(report)
        print(f"Results saved to {output_path}/")


def main():
    harness = EvaluationHarness()
    print("Building dataset...")
    data = harness._build_dataset()
    print(f"Failed attempts for evaluation: {len(data)}")

    print("Training classifier...")
    classifier = harness.train_classifier(data)

    _, test_data = train_test_split(
        data, test_size=0.2, random_state=42, stratify=data["category"]
    )
    classification_metrics = harness.measure_classification(classifier, test_data)
    print(f"F1 weighted: {classification_metrics['f1_weighted']:.3f}")

    print("Running ablation study...")
    ablation_results = harness.run_ablation_study(data, classifier)
    report = harness.generate_evaluation_report(ablation_results, classification_metrics)
    harness.save_results(ablation_results, report)

    full = ablation_results["full_system"]["recovery_rate"]["mean"]
    base = ablation_results["baseline"]["recovery_rate"]["mean"]
    print(f"\nFull system recovery: {full:.1%} | Baseline: {base:.1%} | Lift: +{(full-base):.1%}")


if __name__ == "__main__":
    main()
