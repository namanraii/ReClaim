"""
Synthetic Data Generator for Reclaim
Grounded in NPCI/RBI rules documented in METHODOLOGY.md
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import uuid
from typing import List, Dict, Tuple


class SyntheticDataGenerator:
    """
    Generates synthetic UPI AutoPay mandate data grounded in real NPCI/RBI rules.
    See data/METHODOLOGY.md for detailed rule documentation.
    """

    # Real Indian banks for diversity
    BANKS = [
        "SBI", "HDFC", "ICICI", "AXIS", "KOTAK", 
        "PNB", "BOB", "BANK_OF_BARODA", "UNION", "INDIAN"
    ]

    # PSP apps
    PSP_APPS = ["GPay", "PhonePe", "Paytm", "BHIM", "AmazonPay"]

    # Mandate frequencies
    FREQUENCIES = ["daily", "weekly", "monthly", "quarterly"]

    # Mandate categories for PIN re-auth exceptions
    CATEGORIES = [
        "subscription", "insurance", "mutual_fund_sip", 
        "credit_card_bill", "utility", "emi"
    ]

    # Failure categories matching our classifier
    FAILURE_CATEGORIES = [
        "NPCI_WINDOW_VIOLATION",
        "LOW_BALANCE", 
        "PORTABILITY_BREAKAGE",
        "PRE_DEBIT_OPT_OUT",
        "BANK_TECHNICAL_DECLINE",
        "PIN_REAUTH_REQUIRED"
    ]

    def __init__(self, num_mandates: int = 500, start_date: datetime = None):
        self.num_mandates = num_mandates
        self.start_date = start_date or datetime(2026, 1, 1)
        self.rng = np.random.RandomState(42)  # For reproducibility

    def generate_mandates(self) -> pd.DataFrame:
        """Generate synthetic mandate data"""
        mandates = []

        for i in range(self.num_mandates):
            mandate = {
                "id": str(uuid.uuid4()),
                "customer_vpa": f"customer{i}@{random.choice(['okhdfc', 'okicici', 'oksbi', 'ybl', 'paytm'])}",
                "merchant_id": f"merchant_{random.randint(1, 20)}",
                "bank_code": random.choice(self.BANKS),
                "psp_app": random.choice(self.PSP_APPS),
                "amount": self._generate_amount(),
                "frequency": random.choice(self.FREQUENCIES),
                "category": random.choice(self.CATEGORIES),
                "created_at": self._generate_created_at(),
                "status": "ACTIVE",
                "pin_reauth_required": False,  # Will be calculated
                "consent_for_outreach": random.random() > 0.1,  # 90% consent
                "portability_cooldown_until": None
            }

            # Set expiry date (1-2 years from creation)
            mandate["expires_at"] = mandate["created_at"] + timedelta(
                days=random.randint(365, 730)
            )

            # Calculate PIN re-auth requirement
            mandate["pin_reauth_required"] = self._requires_pin_reauth(
                mandate["amount"], mandate["category"]
            )

            mandates.append(mandate)

        return pd.DataFrame(mandates)

    def generate_debit_attempts(self, mandates_df: pd.DataFrame) -> pd.DataFrame:
        """Generate debit attempts for mandates"""
        attempts = []

        for _, mandate in mandates_df.iterrows():
            num_attempts = self._generate_num_attempts(mandate)

            for attempt_num in range(1, num_attempts + 1):
                scheduled_time = self._generate_scheduled_time(
                    mandate["created_at"], 
                    mandate["frequency"],
                    attempt_num
                )

                # Determine if this attempt succeeds or fails
                success_probability = self._calculate_success_probability(
                    mandate, scheduled_time, attempt_num
                )

                is_success = self.rng.random() < success_probability

                attempt = {
                    "id": str(uuid.uuid4()),
                    "mandate_id": mandate["id"],
                    "scheduled_at": scheduled_time,
                    "executed_at": scheduled_time + timedelta(minutes=random.randint(1, 30)),
                    "amount": mandate["amount"],
                    "attempt_number": attempt_num,
                    "idempotency_key": str(uuid.uuid4()),
                    "status": "SUCCESS" if is_success else "FAILED",
                    "response_code": "SUCCESS" if is_success else self._generate_error_code(),
                    "response_message": "Debit successful" if is_success else "Debit failed"
                }

                attempts.append(attempt)

                # If successful, update last successful debit
                if is_success:
                    mandates_df.loc[mandates_df["id"] == mandate["id"], "last_successful_debit"] = scheduled_time

                # If failed and not last attempt, generate failure event
                if not is_success and attempt_num < num_attempts:
                    failure_category = self._classify_failure(mandate, scheduled_time, attempt_num)
                    # Will be added to failure_events separately

        return pd.DataFrame(attempts)

    def generate_failure_events(self, attempts_df: pd.DataFrame, mandates_df: pd.DataFrame) -> pd.DataFrame:
        """Generate failure events for failed debit attempts"""
        failed_attempts = attempts_df[attempts_df["status"] == "FAILED"]
        failure_events = []

        for _, attempt in failed_attempts.iterrows():
            mandate = mandates_df[mandates_df["id"] == attempt["mandate_id"]].iloc[0]

            category = self._classify_failure(mandate, attempt["scheduled_at"], attempt["attempt_number"])
            confidence = self._generate_confidence(category)

            failure_event = {
                "id": str(uuid.uuid4()),
                "debit_attempt_id": attempt["id"],
                "category": category,
                "confidence": confidence,
                "shap_explanation": self._generate_shap_explanation(category),
                "detected_at": attempt["executed_at"],
                "raw_error_code": attempt["response_code"],
                "context": self._generate_failure_context(category, mandate)
            }

            failure_events.append(failure_event)

        return pd.DataFrame(failure_events)

    def _generate_amount(self) -> float:
        """Generate realistic debit amounts"""
        # Weighted towards common recurring payment amounts
        common_amounts = [99, 199, 299, 499, 999, 1499, 1999, 4999, 9999]
        if random.random() < 0.3:
            return float(random.choice(common_amounts))
        else:
            return float(random.randint(100, 50000))

    def _generate_created_at(self) -> datetime:
        """Generate mandate creation date within realistic range"""
        days_ago = random.randint(30, 365)
        return self.start_date - timedelta(days=days_ago)

    def _generate_num_attempts(self, mandate: Dict) -> int:
        """Generate number of debit attempts based on mandate age and frequency"""
        mandate_age_days = (self.start_date - mandate["created_at"]).days

        if mandate["frequency"] == "daily":
            return min(mandate_age_days, 30)  # Cap at 30 attempts
        elif mandate["frequency"] == "weekly":
            return min(mandate_age_days // 7, 12)
        elif mandate["frequency"] == "monthly":
            return min(mandate_age_days // 30, 6)
        else:  # quarterly
            return min(mandate_age_days // 90, 4)

    def _generate_scheduled_time(self, created_at: datetime, frequency: str, attempt_num: int) -> datetime:
        """Generate scheduled debit time based on frequency"""
        if frequency == "daily":
            days_to_add = attempt_num
        elif frequency == "weekly":
            days_to_add = attempt_num * 7
        elif frequency == "monthly":
            days_to_add = attempt_num * 30
        else:  # quarterly
            days_to_add = attempt_num * 90

        # Add to creation date
        base_time = created_at + timedelta(days=days_to_add)

        # Add realistic scheduling (early morning batch processing)
        # Most banks process batches between 2 AM - 8 AM
        hour = random.randint(2, 8)
        minute = random.randint(0, 59)

        return base_time.replace(hour=hour, minute=minute)

    def _calculate_success_probability(self, mandate: Dict, scheduled_time: datetime, attempt_num: int) -> float:
        """Calculate success probability based on multiple factors"""
        base_prob = 0.80  # Base success rate

        # Bank-specific variance (some banks have higher success rates)
        bank_multipliers = {
            "SBI": 0.95, "HDFC": 0.92, "ICICI": 0.90, "AXIS": 0.88,
            "KOTAK": 0.87, "PNB": 0.85, "BOB": 0.83, "BANK_OF_BARODA": 0.83,
            "UNION": 0.80, "INDIAN": 0.78
        }
        base_prob *= bank_multipliers.get(mandate["bank_code"], 0.85)

        # Time-of-day impact (early morning better than peak hours)
        hour = scheduled_time.hour
        if 10 <= hour <= 13 or 17 <= hour <= 21:  # Peak hours
            base_prob *= 0.7  # Reduced success in peak hours

        # Amount impact (higher amounts have slightly lower success)
        if mandate["amount"] > 15000:
            base_prob *= 0.9

        # Attempt number impact (retries have lower success)
        if attempt_num > 1:
            base_prob *= 0.7  # First retry
        if attempt_num > 2:
            base_prob *= 0.5  # Second retry
        if attempt_num > 3:
            base_prob *= 0.3  # Third retry

        # Month-end balance issues (salaries credited start of month)
        day_of_month = scheduled_time.day
        if day_of_month > 25:  # Month-end
            base_prob *= 0.85

        return max(0.1, min(0.95, base_prob))

    def _classify_failure(self, mandate: Dict, scheduled_time: datetime, attempt_num: int) -> str:
        """Classify failure reason based on context"""
        hour = scheduled_time.hour
        day_of_month = scheduled_time.day

        # Peak hour violation
        if 10 <= hour <= 13 or 17 <= hour <= 21:
            return "NPCI_WINDOW_VIOLATION"

        # Month-end low balance
        if day_of_month > 25 and random.random() < 0.4:
            return "LOW_BALANCE"

        # PIN re-auth required
        if mandate["pin_reauth_required"] and random.random() < 0.3:
            return "PIN_REAUTH_REQUIRED"

        # Portability breakage (random, as it's unpredictable)
        if random.random() < 0.05:
            return "PORTABILITY_BREAKAGE"

        # Pre-debit opt-out
        if random.random() < 0.08:
            return "PRE_DEBIT_OPT_OUT"

        # Default to bank technical decline
        return "BANK_TECHNICAL_DECLINE"

    def _generate_error_code(self) -> str:
        """Generate realistic UPI error codes"""
        error_codes = [
            "U51", "U52", "U53",  # Bank-related errors
            "U71", "U72",        # Mandate-related errors
            "U91", "U92",        # Technical errors
            "U33", "U34"         # Balance-related errors
        ]
        return random.choice(error_codes)

    def _generate_confidence(self, category: str) -> float:
        """Generate confidence score for classification"""
        # Some categories are easier to classify than others
        base_confidence = {
            "NPCI_WINDOW_VIOLATION": 0.95,
            "PIN_REAUTH_REQUIRED": 0.92,
            "LOW_BALANCE": 0.85,
            "BANK_TECHNICAL_DECLINE": 0.78,
            "PORTABILITY_BREAKAGE": 0.82,
            "PRE_DEBIT_OPT_OUT": 0.88
        }
        return base_confidence.get(category, 0.80) + random.uniform(-0.05, 0.05)

    def _generate_shap_explanation(self, category: str) -> str:
        """Generate mock SHAP explanation (in real system, this comes from model)"""
        # This is a simplified version - real SHAP values would be more complex
        explanation = {
            "NPCI_WINDOW_VIOLATION": {
                "hour_of_day": 0.4,
                "day_of_week": 0.1,
                "bank_code": 0.05
            },
            "LOW_BALANCE": {
                "day_of_month": 0.5,
                "amount": 0.3,
                "historical_success_rate": 0.2
            },
            "PIN_REAUTH_REQUIRED": {
                "amount": 0.6,
                "category": 0.3,
                "bank_code": 0.1
            }
        }
        return str(explanation.get(category, {}))

    def _generate_failure_context(self, category: str, mandate: Dict) -> str:
        """Generate additional context for failure"""
        context = {
            "bank_code": mandate["bank_code"],
            "psp_app": mandate["psp_app"],
            "amount": mandate["amount"],
            "category": category
        }
        return str(context)

    def _requires_pin_reauth(self, amount: float, category: str) -> bool:
        """Check if mandate requires PIN re-authentication"""
        # Exception categories with higher threshold
        if category in ["insurance", "mutual_fund_sip", "credit_card_bill"]:
            return amount > 100000  # ₹1,00,000
        return amount > 15000  # ₹15,000

    def generate_full_dataset(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Generate complete synthetic dataset"""
        print(f"Generating {self.num_mandates} synthetic mandates...")
        mandates_df = self.generate_mandates()
        print(f"Generated {len(mandates_df)} mandates")

        print("Generating debit attempts...")
        attempts_df = self.generate_debit_attempts(mandates_df)
        print(f"Generated {len(attempts_df)} debit attempts")

        print("Generating failure events...")
        failure_events_df = self.generate_failure_events(attempts_df, mandates_df)
        print(f"Generated {len(failure_events_df)} failure events")

        return mandates_df, attempts_df, failure_events_df

    def save_to_csv(self, mandates_df: pd.DataFrame, attempts_df: pd.DataFrame, 
                   failure_events_df: pd.DataFrame, output_dir: str = "data"):
        """Save generated datasets to CSV files"""
        import os
        os.makedirs(output_dir, exist_ok=True)

        mandates_df.to_csv(f"{output_dir}/mandates.csv", index=False)
        attempts_df.to_csv(f"{output_dir}/debit_attempts.csv", index=False)
        failure_events_df.to_csv(f"{output_dir}/failure_events.csv", index=False)

        print(f"Saved datasets to {output_dir}/")


if __name__ == "__main__":
    # Generate synthetic data
    generator = SyntheticDataGenerator(num_mandates=500)
    mandates_df, attempts_df, failure_events_df = generator.generate_full_dataset()
    generator.save_to_csv(mandates_df, attempts_df, failure_events_df)

    # Print summary statistics
    print("\n=== Dataset Summary ===")
    print(f"Total Mandates: {len(mandates_df)}")
    print(f"Total Debit Attempts: {len(attempts_df)}")
    print(f"Total Failure Events: {len(failure_events_df)}")
    print(f"Success Rate: {len(attempts_df[attempts_df['status'] == 'SUCCESS']) / len(attempts_df):.2%}")

    print("\n=== Failure Category Distribution ===")
    print(failure_events_df['category'].value_counts())
