"""
Database seeding — loads synthetic data and trains classifier if needed.
"""

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Add data/ to path for synthetic generator
BACKEND_ROOT = Path(__file__).parent.parent
for data_path in [BACKEND_ROOT.parent / "data", BACKEND_ROOT / "data"]:
    if data_path.exists():
        sys.path.insert(0, str(data_path))
        break

from sqlalchemy.orm import Session

from app.db import SessionLocal, engine, Base
from app.db.models import (
    Mandate, MandateStatus, DebitAttempt, DebitStatus,
    FailureEvent, FailureCategory, RecoveryOutcome, RecoveryState, AuditLog,
)
from app.compliance import NPCIComplianceEngine


def _ensure_model():
    """Train classifier if artifact is missing."""
    from app.models.service import MODEL_PATH
    if MODEL_PATH.exists():
        return
    print("Training classifier (first run)...")
    import subprocess
    backend_dir = Path(__file__).parent.parent.parent
    subprocess.run(
        [sys.executable, "-m", "scripts.train_classifier"],
        cwd=str(backend_dir),
        check=True,
    )


def seed_database(force: bool = False) -> dict:
    """Seed database with synthetic mandates, attempts, and failure events."""
    Base.metadata.create_all(bind=engine)
    _ensure_model()

    db: Session = SessionLocal()
    try:
        existing = db.query(Mandate).count()
        if existing > 0 and not force:
            print(f"Database already has {existing} mandates — skipping seed.")
            return {"seeded": False, "existing_mandates": existing}

        if force:
            db.query(AuditLog).delete()
            db.query(RecoveryOutcome).delete()
            db.query(FailureEvent).delete()
            db.query(DebitAttempt).delete()
            db.query(Mandate).delete()
            db.commit()

        from synthetic_generation import SyntheticDataGenerator

        generator = SyntheticDataGenerator(num_mandates=500)
        mandates_df, attempts_df, failure_events_df = generator.generate_full_dataset()
        compliance = NPCIComplianceEngine()

        mandate_map = {}
        for _, row in mandates_df.iterrows():
            pin_required = compliance.requires_pin_reauth(row["amount"], row["category"])
            mandate = Mandate(
                id=row["id"],
                customer_vpa=row["customer_vpa"],
                merchant_id=row["merchant_id"],
                bank_code=row["bank_code"],
                psp_app=row["psp_app"],
                amount=float(row["amount"]),
                frequency=row["frequency"],
                category=row["category"],
                status=MandateStatus.ACTIVE,
                created_at=row["created_at"],
                expires_at=row["expires_at"],
                last_successful_debit=row.get("last_successful_debit") if "last_successful_debit" in row and pd_notna(row.get("last_successful_debit")) else None,
                pin_reauth_required=pin_required,
                consent_for_outreach=bool(row["consent_for_outreach"]),
                portability_cooldown_until=row.get("portability_cooldown_until"),
            )
            db.add(mandate)
            mandate_map[row["id"]] = mandate

        attempt_map = {}
        for _, row in attempts_df.iterrows():
            attempt = DebitAttempt(
                id=row["id"],
                mandate_id=row["mandate_id"],
                scheduled_at=row["scheduled_at"],
                executed_at=row.get("executed_at"),
                amount=float(row["amount"]),
                status=DebitStatus(row["status"]),
                attempt_number=int(row["attempt_number"]),
                idempotency_key=row["idempotency_key"],
                response_code=row.get("response_code"),
                response_message=row.get("response_message"),
            )
            db.add(attempt)
            attempt_map[row["id"]] = attempt

        recovered_count = 0
        for _, row in failure_events_df.iterrows():
            try:
                category = FailureCategory(row["category"])
            except ValueError:
                continue
            fe = FailureEvent(
                id=row["id"],
                debit_attempt_id=row["debit_attempt_id"],
                category=category,
                confidence=float(row["confidence"]),
                shap_explanation=row.get("shap_explanation"),
                detected_at=row["detected_at"],
                raw_error_code=row.get("raw_error_code"),
                context=row.get("context"),
            )
            db.add(fe)

        # Create recovery outcomes (~59% recovered, matches measured evaluation)
        failed_mandate_ids = list(attempts_df[attempts_df["status"] == "FAILED"]["mandate_id"].unique())
        n_recovered = int(len(failed_mandate_ids) * 0.59)
        for mid in failed_mandate_ids[:n_recovered]:
            outcome = RecoveryOutcome(
                id=str(uuid.uuid4()),
                mandate_id=mid,
                state=RecoveryState.RECOVERED,
                recovery_attempts=2,
                final_amount_recovered=float(mandates_df[mandates_df["id"] == mid]["amount"].iloc[0]),
                final_outcome="Recovery successful",
            )
            db.add(outcome)
            recovered_count += 1

        for mid in failed_mandate_ids[n_recovered:]:
            outcome = RecoveryOutcome(
                id=str(uuid.uuid4()),
                mandate_id=mid,
                state=RecoveryState.EXHAUSTED,
                recovery_attempts=4,
                final_outcome="All retry attempts exhausted",
            )
            db.add(outcome)

        db.commit()
        stats = {
            "seeded": True,
            "mandates": len(mandates_df),
            "attempts": len(attempts_df),
            "failure_events": len(failure_events_df),
            "recovered": recovered_count,
        }
        print(f"Seeded: {stats}")
        return stats
    finally:
        db.close()


def pd_notna(val):
    import pandas as pd
    return val is not None and pd.notna(val)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Re-seed even if data exists")
    args = parser.parse_args()
    seed_database(force=args.force)
