"""
Isolation Forest for transaction anomaly detection.

Key architectural decision: models are trained PER TENANT (never globally).
A global model trained on all tenants would:
1. Violate the Chinese Wall (one tenant's data influences another's scores)
2. Perform poorly due to distribution mismatch between different industries

Parameters from the architecture doc:
  n_estimators = 200
  contamination = 'auto'
  max_samples = 256    (critical: larger values increase runtime super-linearly)
"""

import numpy as np
import pickle
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import MinMaxScaler
from dataclasses import dataclass, field


@dataclass
class IsolationForestModel:
    """Wrapper around scikit-learn IsolationForest with normalization."""
    model: IsolationForest = field(default=None)
    scaler: MinMaxScaler = field(default=None)
    score_min: float = -1.0    # decision_function min from training set
    score_max: float = 0.5     # decision_function max from training set
    feature_dim: int = 12
    tenant_id: str = ""
    version: str = "1.0.0"
    training_sample_count: int = 0

    def predict_scores(self, features: np.ndarray) -> np.ndarray:
        """
        Returns anomaly scores in [0, 1] where higher = more anomalous.

        sklearn's decision_function returns negative values for anomalies,
        positive for normal. We invert and normalize to [0, 1].
        """
        if self.model is None:
            raise RuntimeError("Model not trained")
        raw_scores = self.model.decision_function(features)
        # Invert: more negative = more anomalous = higher score after inversion
        inverted = -raw_scores
        # Normalize to [0, 1] using training set bounds
        norm = np.clip(
            (inverted - (-self.score_max)) / ((-self.score_min) - (-self.score_max) + 1e-8),
            0.0, 1.0,
        )
        return norm.astype(np.float32)

    def is_anomaly(self, features: np.ndarray) -> np.ndarray:
        """Returns boolean array: True = predicted anomaly."""
        if self.model is None:
            raise RuntimeError("Model not trained")
        return self.model.predict(features) == -1


def train_isolation_forest(
    features: np.ndarray,
    tenant_id: str,
    framework: str = 'soc2',
    n_estimators: int = 200,
    max_samples: int = 256,
    random_state: int = 42,
) -> IsolationForestModel:
    """
    Train an Isolation Forest on a tenant's feature matrix.

    max_samples=256 is deliberately small — it's the critical performance
    parameter. From the architecture doc: "larger values increase accuracy
    marginally but increase prediction time super-linearly."
    """
    if features.shape[0] < 10:
        raise ValueError(f"Need at least 10 samples to train, got {features.shape[0]}")

    model = IsolationForest(
        n_estimators=n_estimators,
        contamination='auto',
        max_samples=min(max_samples, features.shape[0]),
        random_state=random_state,
        n_jobs=-1,  # Use all CPU cores
    )
    model.fit(features)

    # Compute score bounds on the training set for normalization
    raw_scores = model.decision_function(features)
    score_min = float(raw_scores.min())
    score_max = float(raw_scores.max())

    return IsolationForestModel(
        model=model,
        score_min=score_min,
        score_max=score_max,
        feature_dim=features.shape[1],
        tenant_id=tenant_id,
        training_sample_count=features.shape[0],
    )


def serialize_model(if_model: IsolationForestModel) -> bytes:
    """Serialize to bytes for MLflow artifact storage."""
    return pickle.dumps(if_model)


def deserialize_model(data: bytes) -> IsolationForestModel:
    """Deserialize from bytes."""
    return pickle.loads(data)
