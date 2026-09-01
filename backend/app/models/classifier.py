"""
Failure Classification Model
XGBoost/LightGBM classifier with SHAP explainability for UPI AutoPay mandate failures
"""

import pandas as pd
import numpy as np
import xgboost as xgb
import lightgbm as lgb
import shap
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.utils.class_weight import compute_sample_weight
import joblib
import json
from typing import Dict, Tuple, Optional, List
from pathlib import Path


class FailureClassifier:
    """
    Classifies UPI AutoPay mandate failures into 6 categories:
    1. NPCI_WINDOW_VIOLATION
    2. LOW_BALANCE
    3. PORTABILITY_BREAKAGE
    4. PRE_DEBIT_OPT_OUT
    5. BANK_TECHNICAL_DECLINE
    6. PIN_REAUTH_REQUIRED
    """

    FAILURE_CATEGORIES = [
        "NPCI_WINDOW_VIOLATION",
        "LOW_BALANCE",
        "PORTABILITY_BREAKAGE",
        "PRE_DEBIT_OPT_OUT",
        "BANK_TECHNICAL_DECLINE",
        "PIN_REAUTH_REQUIRED"
    ]

    def __init__(self, model_type: str = "xgboost", random_state: int = 42):
        """
        Initialize classifier
        
        Args:
            model_type: "xgboost" or "lightgbm"
            random_state: Random seed for reproducibility
        """
        self.model_type = model_type
        self.random_state = random_state
        self.model = None
        self.label_encoder = LabelEncoder()
        self.feature_encoders = {}
        self.shap_explainer = None
        self.feature_names = None

    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Engineer features from raw mandate and debit attempt data
        
        Args:
            df: DataFrame with mandate and debit attempt columns
            
        Returns:
            DataFrame with engineered features
        """
        features = df.copy()

        # Time-based features
        if 'scheduled_at' in features.columns:
            features['hour_of_day'] = pd.to_datetime(features['scheduled_at']).dt.hour
            features['day_of_week'] = pd.to_datetime(features['scheduled_at']).dt.dayofweek
            features['day_of_month'] = pd.to_datetime(features['scheduled_at']).dt.day

        # Amount-based features
        if 'amount' in features.columns:
            features['amount_log'] = np.log1p(features['amount'])
            features['amount_band'] = pd.cut(
                features['amount'],
                bins=[0, 1000, 5000, 15000, 50000, float('inf')],
                labels=['0-1k', '1k-5k', '5k-15k', '15k-50k', '50k+']
            )

        # Attempt-based features
        if 'attempt_number' in features.columns:
            features['is_retry'] = (features['attempt_number'] > 1).astype(int)
            features['retry_sequence'] = features['attempt_number'] - 1

        # Bank success rate proxy (based on historical data)
        if 'bank_code' in features.columns:
            bank_success_rates = {
                'SBI': 0.95, 'HDFC': 0.92, 'ICICI': 0.90, 'AXIS': 0.88,
                'KOTAK': 0.87, 'PNB': 0.85, 'BOB': 0.83, 'BANK_OF_BARODA': 0.83,
                'UNION': 0.80, 'INDIAN': 0.78
            }
            features['bank_success_rate'] = features['bank_code'].map(bank_success_rates).fillna(0.85)

        # PIN re-auth requirement
        if 'pin_reauth_required' in features.columns:
            features['pin_reauth_required'] = features['pin_reauth_required'].astype(int)

        # Mandate age
        if 'created_at' in features.columns and 'scheduled_at' in features.columns:
            features['mandate_age_days'] = (
                pd.to_datetime(features['scheduled_at']) - pd.to_datetime(features['created_at'])
            ).dt.days

        # Days since last success
        if 'last_successful_debit' in features.columns and 'scheduled_at' in features.columns:
            features['days_since_last_success'] = (
                pd.to_datetime(features['scheduled_at']) - pd.to_datetime(features['last_successful_debit'])
            ).dt.days
            features['days_since_last_success'] = features['days_since_last_success'].fillna(365)

        # Portability cooldown signal
        if 'portability_cooldown_until' in features.columns:
            features['in_portability_cooldown'] = features['portability_cooldown_until'].notna().astype(int)

        # Consent for outreach — key signal for PRE_DEBIT_OPT_OUT separability
        if 'consent_for_outreach' in features.columns:
            features['consent_for_outreach'] = features['consent_for_outreach'].astype(int)

        return features

    def encode_features(self, df: pd.DataFrame, fit: bool = True, exclude_cols: list = None) -> pd.DataFrame:
        """
        Encode categorical features
        
        Args:
            df: DataFrame with categorical features
            fit: Whether to fit encoders (True for training, False for inference)
            exclude_cols: Columns to skip encoding (e.g. target column)
            
        Returns:
            DataFrame with encoded features
        """
        encoded = df.copy()
        skip = set(exclude_cols or [])
        categorical_columns = encoded.select_dtypes(include=['object', 'category']).columns.tolist()

        for col in categorical_columns:
            if col in skip:
                continue
            if col not in ['id', 'mandate_id', 'customer_vpa', 'merchant_id', 'response_code', 'response_message']:
                if fit:
                    self.feature_encoders[col] = LabelEncoder()
                    encoded[col] = self.feature_encoders[col].fit_transform(encoded[col].astype(str))
                else:
                    if col in self.feature_encoders:
                        # Handle unseen categories
                        encoded[col] = encoded[col].astype(str).map(
                            lambda x: x if x in self.feature_encoders[col].classes_ else 'unknown'
                        )
                        # Add 'unknown' to classes if not present
                        if 'unknown' not in self.feature_encoders[col].classes_:
                            self.feature_encoders[col].classes_ = np.append(
                                self.feature_encoders[col].classes_, 'unknown'
                            )
                        encoded[col] = self.feature_encoders[col].transform(encoded[col])
                    else:
                        encoded[col] = 0  # Default encoding if encoder not found

        return encoded

    def train(self, df: pd.DataFrame, target_column: str = 'category', test_size: float = 0.2) -> Dict:
        """
        Train the classifier
        
        Args:
            df: Training data with features and target
            target_column: Name of target column
            test_size: Proportion of data for testing
            
        Returns:
            Training metrics dictionary
        """
        # Prepare features
        features_df = self.prepare_features(df)
        y = features_df[target_column].astype(str)

        # Encode features (target column excluded from encoding)
        features_df = self.encode_features(features_df, fit=True, exclude_cols=[target_column])
        
        # Select feature columns (exclude non-feature columns)
        exclude_cols = ['id', 'mandate_id', 'customer_vpa', 'merchant_id', 'debit_attempt_id',
                       'scheduled_at', 'executed_at', 'created_at', 'expires_at', 'last_successful_debit',
                       'status', 'response_code', 'response_message', 'detected_at', 'context',
                       'shap_explanation', 'raw_error_code', target_column,
                       'mandate_category', 'id_mandate', 'id_m',
                       'portability_cooldown_until', 'expires_at_m']
        
        feature_cols = [col for col in features_df.columns if col not in exclude_cols]
        self.feature_names = feature_cols
        
        X = features_df[feature_cols]
        y_encoded = self.label_encoder.fit_transform(y)
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y_encoded, test_size=test_size, random_state=self.random_state, stratify=y_encoded
        )

        # Balanced sample weights to handle class imbalance (~19:1 majority:minority)
        sample_weights = compute_sample_weight(class_weight="balanced", y=y_train)
        
        # Train model
        if self.model_type == "xgboost":
            self.model = xgb.XGBClassifier(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=self.random_state,
                eval_metric='mlogloss',
                nthread=1,  # single-threaded for full reproducibility
            )
        else:  # lightgbm
            self.model = lgb.LGBMClassifier(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=self.random_state,
                verbose=-1,
                class_weight="balanced",
            )
        
        if self.model_type == "xgboost":
            self.model.fit(X_train, y_train, sample_weight=sample_weights)
        else:
            self.model.fit(X_train, y_train)
        
        # Initialize SHAP explainer
        self.shap_explainer = shap.TreeExplainer(self.model)
        
        # Evaluate
        y_pred = self.model.predict(X_test)
        
        metrics = {
            'accuracy': (y_pred == y_test).mean(),
            'f1_macro': f1_score(y_test, y_pred, average='macro', zero_division=0),
            'f1_weighted': f1_score(y_test, y_pred, average='weighted', zero_division=0),
            'classification_report': classification_report(
                y_test, y_pred,
                target_names=self.label_encoder.classes_,
                output_dict=True,
                zero_division=0,
            ),
            'confusion_matrix': confusion_matrix(
                y_test, y_pred, labels=range(len(self.label_encoder.classes_))
            ).tolist(),
            'label_names': self.label_encoder.classes_.tolist(),
        }
        
        return metrics

    def predict(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Make predictions on new data
        
        Args:
            df: DataFrame with features
            
        Returns:
            Tuple of (predicted_classes, confidence_scores)
        """
        # Prepare features
        features_df = self.prepare_features(df)
        
        # Encode features
        features_df = self.encode_features(features_df, fit=False)
        
        # Select feature columns — align to training feature set
        for col in self.feature_names:
            if col not in features_df.columns:
                features_df[col] = 0
        X = features_df[self.feature_names]
        
        # Make predictions
        predictions_encoded = self.model.predict(X)
        confidence_scores = self.model.predict_proba(X)

        # Decode predictions
        predictions = self.label_encoder.inverse_transform(predictions_encoded.astype(int))
        
        return predictions, confidence_scores

    def explain_prediction(self, df: pd.DataFrame, index: int = 0) -> Dict:
        """
        Generate SHAP explanation for a single prediction
        
        Args:
            df: DataFrame with features
            index: Index of row to explain
            
        Returns:
            Dictionary with SHAP values and feature importance
        """
        # Prepare features
        features_df = self.prepare_features(df)

        # Encode features
        features_df = self.encode_features(features_df, fit=False)

        for col in self.feature_names:
            if col not in features_df.columns:
                features_df[col] = 0
        X = features_df[self.feature_names]

        # Get SHAP values
        shap_values = self.shap_explainer.shap_values(X.iloc[[index]])

        # Get the predicted class index for this sample so we explain the actual prediction,
        # not an arbitrary class. Using signed values (no abs) preserves directional info:
        # positive = feature pushed toward this class, negative = pushed against.
        predicted_encoded = int(self.model.predict(X.iloc[[index]])[0])
        class_idx = predicted_encoded  # direct index into the classes dimension

        # Normalise shap_values into a (n_features, n_classes) matrix regardless of SHAP version
        if isinstance(shap_values, list):
            # Old SHAP API: list of (n_samples, n_features) arrays, one per class
            # shap_values[class_idx][0] is the feature vector for class class_idx, sample 0
            sample_shap_per_class = np.stack([sv[0] for sv in shap_values], axis=1)  # (n_features, n_classes)
        elif len(shap_values.shape) == 3:
            # New SHAP API: (n_samples, n_features, n_classes)
            sample_shap_per_class = shap_values[0]  # (n_features, n_classes)
        else:
            # Binary or unexpected: (n_samples, n_features) — treat as single class
            sample_shap_per_class = shap_values[0].reshape(-1, 1)
            class_idx = 0

        # Slice to the predicted class — signed values, not max-across-all-classes
        class_shap = sample_shap_per_class[:, class_idx]  # (n_features,)

        feature_importance = {
            feat: float(class_shap[idx])
            for idx, feat in enumerate(self.feature_names)
        }
        raw_shap = class_shap.tolist()

        base_val = self.shap_explainer.expected_value
        if isinstance(base_val, (list, np.ndarray)):
            base_val = float(base_val[class_idx])
        else:
            base_val = float(base_val)

        explanation = {
            'feature_names': self.feature_names,
            'shap_values': raw_shap,
            'base_value': base_val,
            'feature_importance': feature_importance,
            'predicted_class_idx': class_idx,
            'predicted_class_label': self.label_encoder.inverse_transform([class_idx])[0],
        }

        return explanation

    def save_model(self, path: str):
        """Save trained model and encoders"""
        model_data = {
            'model': self.model,
            'label_encoder': self.label_encoder,
            'feature_encoders': self.feature_encoders,
            'feature_names': self.feature_names,
            'model_type': self.model_type,
            'random_state': self.random_state
        }
        joblib.dump(model_data, path)
        print(f"Model saved to {path}")

    def load_model(self, path: str):
        """Load trained model and encoders"""
        model_data = joblib.load(path)
        self.model = model_data['model']
        self.label_encoder = model_data['label_encoder']
        self.feature_encoders = model_data['feature_encoders']
        self.feature_names = model_data['feature_names']
        self.model_type = model_data['model_type']
        self.random_state = model_data['random_state']
        
        # Reinitialize SHAP explainer
        self.shap_explainer = shap.TreeExplainer(self.model)
        print(f"Model loaded from {path}")


if __name__ == "__main__":
    # Example usage
    print("Failure Classifier Module")
    print("This module provides XGBoost/LightGBM classification with SHAP explainability")
    print("for UPI AutoPay mandate failure root cause analysis.")
