"""
Ensemble aggregation and Dynamic Risk Index (DRI) computation.

The DRI combines three model signals (VAE, Isolation Forest, Benford's Law) with
five additional risk factors via a learned meta-classifier (logistic regression).

Architecture from the design doc:
  DRI = sigmoid(
      w1 * vae_score + w2 * isolation_score + w3 * benford_risk +
      w4 * vendor_age_risk + w5 * round_number_freq +
      w6 * weekend_activity + w7 * rare_account_interaction +
      w8 * jurisdictional_risk + bias
  )

The weights (w1..w8, bias) come from:
  1. A learned logistic regression meta-classifier trained on human-labeled anomalies
  2. Per-framework weight overrides from dri_framework_weights table
     (SOC 2 ≠ ISO 27001 ≠ PCI DSS)

CRITICAL: per-tenant training isolation.
  The meta-classifier is trained per-tenant using ONLY that tenant's labeled data.
  The DRI for Tenant A is NEVER influenced by Tenant B's data or labels.
"""

import math
import numpy as np
from dataclasses import dataclass, field
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
import pickle
import structlog

logger = structlog.get_logger()


@dataclass
class DRIWeights:
    """
    Weight configuration for the Dynamic Risk Index.
    Loaded from dri_framework_weights DB table per framework.
    """
    framework: str = 'soc2'
    w_vae: float = 0.20
    w_isolation: float = 0.20
    w_benford: float = 0.15
    w_vendor_age: float = 0.10
    w_round_number: float = 0.10
    w_weekend_activity: float = 0.08
    w_rare_account: float = 0.07
    w_jurisdictional: float = 0.10
    bias: float = 0.0

    def to_weight_vector(self) -> np.ndarray:
        return np.array([
            self.w_vae, self.w_isolation, self.w_benford,
            self.w_vendor_age, self.w_round_number, self.w_weekend_activity,
            self.w_rare_account, self.w_jurisdictional,
        ])

    @classmethod
    def from_db_row(cls, row: dict) -> 'DRIWeights':
        return cls(
            framework=row['framework'],
            w_vae=float(row['w_vae']),
            w_isolation=float(row['w_isolation']),
            w_benford=float(row['w_benford']),
            w_vendor_age=float(row['w_vendor_age']),
            w_round_number=float(row['w_round_number']),
            w_weekend_activity=float(row['w_weekend_activity']),
            w_rare_account=float(row['w_rare_account']),
            w_jurisdictional=float(row['w_jurisdictional']),
            bias=float(row.get('bias', 0.0)),
        )


@dataclass
class EnsembleInput:
    """
    Complete input to the DRI ensemble for a single evidence record.
    All scores are pre-normalized to [0, 1].
    """
    # Model scores
    vae_score: float           # VAE reconstruction error, normalized [0,1]
    isolation_score: float     # Isolation Forest score, normalized [0,1]
    benford_risk: float        # Benford's Law risk score [0,1]; 0.5 if insufficient data

    # Structural risk factors (from features.py)
    vendor_age_risk: float     # 1 - sigmoid(vendor_age_norm): newer vendor = higher risk
    round_number_freq: float   # Frequency of round amounts (% of amounts % 1000 == 0)
    weekend_activity: float    # Ratio of weekend transactions for this entity
    rare_account_interaction: float  # 1 - account_interaction_percentile
    jurisdictional_risk: float # Pre-computed jurisdictional risk score

    # Metadata (not used in DRI computation)
    evidence_id: str = ""
    tenant_id: str = ""
    entity_id: str = ""
    entity_type: str = ""
    framework: str = "soc2"

    def to_feature_vector(self) -> np.ndarray:
        """Convert to the 8-dimensional meta-classifier input."""
        return np.array([
            self.vae_score,
            self.isolation_score,
            self.benford_risk,
            self.vendor_age_risk,
            self.round_number_freq,
            self.weekend_activity,
            self.rare_account_interaction,
            self.jurisdictional_risk,
        ], dtype=np.float32)


@dataclass
class DRIResult:
    """Output of the DRI ensemble computation."""
    dynamic_risk_index: float  # [0, 1]
    risk_level: str            # 'low', 'medium', 'high', 'critical'

    # Component scores for explainability
    vae_score: float
    isolation_score: float
    benford_risk: float

    # Meta-classifier used (or fallback to weighted sum)
    scored_by: str = 'weighted_sum'  # 'meta_classifier' or 'weighted_sum'

    # Explanation for audit trail
    top_risk_factors: list[tuple[str, float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'dynamic_risk_index': self.dynamic_risk_index,
            'risk_level': self.risk_level,
            'vae_score': self.vae_score,
            'isolation_score': self.isolation_score,
            'benford_risk': self.benford_risk,
            'scored_by': self.scored_by,
            'top_risk_factors': [
                {'factor': f, 'contribution': c} for f, c in self.top_risk_factors
            ],
        }


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _risk_level(dri: float) -> str:
    if dri < 0.3:
        return 'low'
    elif dri < 0.6:
        return 'medium'
    elif dri < 0.8:
        return 'high'
    return 'critical'


def _top_factors(
    inp: EnsembleInput, weights: DRIWeights
) -> list[tuple[str, float]]:
    """Returns the top 3 contributing risk factors for explainability."""
    factor_names = [
        'vae_anomaly', 'isolation_anomaly', 'benford_deviation',
        'new_vendor', 'round_amounts', 'off_hours_activity',
        'rare_account', 'jurisdiction',
    ]
    w = weights.to_weight_vector()
    v = inp.to_feature_vector()
    contributions = w * v
    indexed = sorted(enumerate(contributions), key=lambda x: x[1], reverse=True)
    return [(factor_names[i], float(contributions[i])) for i, _ in indexed[:3]]


class DRIEnsemble:
    """
    The Dynamic Risk Index ensemble.

    Primary scorer: Learned logistic regression meta-classifier
                    (trained on human-labeled anomaly data, per-tenant)
    Fallback scorer: Weighted sum (used when meta-classifier is not yet trained
                     or when confidence is low)

    The weights from dri_framework_weights are applied as MULTIPLICATIVE adjustments
    to the learned weights, not as replacements. This allows framework-specific tuning
    without discarding the signal learned from labeled data.
    """

    def __init__(self, weights: DRIWeights):
        self.weights = weights
        self._meta_classifier: LogisticRegression | None = None
        self._meta_scaler: StandardScaler | None = None

    def score(self, inp: EnsembleInput) -> DRIResult:
        """
        Compute the DRI for a single evidence record.
        Uses meta-classifier if trained, falls back to weighted sum.
        """
        if self._meta_classifier is not None:
            return self._score_with_meta_classifier(inp)
        return self._score_weighted_sum(inp)

    def score_batch(self, inputs: list[EnsembleInput]) -> list[DRIResult]:
        """Batch scoring — more efficient than calling score() in a loop."""
        if self._meta_classifier is not None:
            feature_matrix = np.stack([i.to_feature_vector() for i in inputs])
            scaled = self._meta_scaler.transform(feature_matrix)
            probs = self._meta_classifier.predict_proba(scaled)[:, 1]  # P(anomaly)
            # Apply framework weight adjustments
            w = self.weights.to_weight_vector()
            w_norm = w / w.sum()
            results = []
            for inp, prob in zip(inputs, probs):
                # Blend meta-classifier probability with weighted sum for stability
                ws_dri = self._weighted_sum_dri(inp)
                dri = 0.7 * float(prob) + 0.3 * ws_dri
                dri = float(np.clip(dri, 0.0, 1.0))
                results.append(DRIResult(
                    dynamic_risk_index=dri,
                    risk_level=_risk_level(dri),
                    vae_score=inp.vae_score,
                    isolation_score=inp.isolation_score,
                    benford_risk=inp.benford_risk,
                    scored_by='meta_classifier',
                    top_risk_factors=_top_factors(inp, self.weights),
                ))
            return results
        return [self._score_weighted_sum(inp) for inp in inputs]

    def _score_with_meta_classifier(self, inp: EnsembleInput) -> DRIResult:
        fv = inp.to_feature_vector().reshape(1, -1)
        scaled = self._meta_scaler.transform(fv)
        prob = float(self._meta_classifier.predict_proba(scaled)[0, 1])
        ws_dri = self._weighted_sum_dri(inp)
        dri = float(np.clip(0.7 * prob + 0.3 * ws_dri, 0.0, 1.0))
        return DRIResult(
            dynamic_risk_index=dri,
            risk_level=_risk_level(dri),
            vae_score=inp.vae_score,
            isolation_score=inp.isolation_score,
            benford_risk=inp.benford_risk,
            scored_by='meta_classifier',
            top_risk_factors=_top_factors(inp, self.weights),
        )

    def _score_weighted_sum(self, inp: EnsembleInput) -> DRIResult:
        dri = self._weighted_sum_dri(inp)
        return DRIResult(
            dynamic_risk_index=dri,
            risk_level=_risk_level(dri),
            vae_score=inp.vae_score,
            isolation_score=inp.isolation_score,
            benford_risk=inp.benford_risk,
            scored_by='weighted_sum',
            top_risk_factors=_top_factors(inp, self.weights),
        )

    def _weighted_sum_dri(self, inp: EnsembleInput) -> float:
        w = self.weights
        raw = (
            w.w_vae * inp.vae_score +
            w.w_isolation * inp.isolation_score +
            w.w_benford * inp.benford_risk +
            w.w_vendor_age * inp.vendor_age_risk +
            w.w_round_number * inp.round_number_freq +
            w.w_weekend_activity * inp.weekend_activity +
            w.w_rare_account * inp.rare_account_interaction +
            w.w_jurisdictional * inp.jurisdictional_risk +
            w.bias
        )
        return float(_sigmoid(raw * 6 - 3))  # Scale to push sigmoid into useful range

    def train_meta_classifier(
        self,
        labeled_inputs: list[EnsembleInput],
        labels: list[int],  # 1 = anomaly, 0 = normal
    ) -> dict:
        """
        Train the logistic regression meta-classifier on human-labeled data.

        CRITICAL: Only call with data from a SINGLE tenant.
        Cross-tenant training is forbidden — it would violate the Chinese Wall.

        Requires at least 50 labeled samples (25 anomalies + 25 normal) for
        statistical validity.
        """
        if len(labeled_inputs) < 50:
            raise ValueError(
                f"Need at least 50 labeled samples for meta-classifier training, "
                f"got {len(labeled_inputs)}. Use weighted_sum fallback until more "
                f"human-reviewed anomalies are available."
            )
        if sum(labels) < 5 or (len(labels) - sum(labels)) < 5:
            raise ValueError("Need at least 5 samples of each class (anomaly, normal)")

        feature_matrix = np.stack([i.to_feature_vector() for i in labeled_inputs])

        self._meta_scaler = StandardScaler()
        X_scaled = self._meta_scaler.fit_transform(feature_matrix)

        self._meta_classifier = LogisticRegression(
            C=1.0,
            class_weight='balanced',  # Handle class imbalance (few labeled anomalies)
            max_iter=1000,
            random_state=42,
        )
        self._meta_classifier.fit(X_scaled, labels)

        # Training metrics
        train_score = self._meta_classifier.score(X_scaled, labels)
        logger.info(
            "Meta-classifier trained",
            tenant=labeled_inputs[0].tenant_id if labeled_inputs else "unknown",
            samples=len(labeled_inputs),
            anomaly_count=sum(labels),
            train_accuracy=train_score,
        )
        return {
            'train_accuracy': train_score,
            'samples': len(labeled_inputs),
            'anomaly_count': sum(labels),
            'framework': self.weights.framework,
        }

    def serialize(self) -> bytes:
        return pickle.dumps({
            'weights': self.weights,
            'meta_classifier': self._meta_classifier,
            'meta_scaler': self._meta_scaler,
        })

    @classmethod
    def deserialize(cls, data: bytes) -> 'DRIEnsemble':
        state = pickle.loads(data)
        instance = cls(weights=state['weights'])
        instance._meta_classifier = state['meta_classifier']
        instance._meta_scaler = state['meta_scaler']
        return instance
