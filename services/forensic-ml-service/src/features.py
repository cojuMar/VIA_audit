"""
Feature extraction for the forensic ML pipeline.

The 12-dimensional feature vector is the input to both the VAE and Isolation Forest.
Every feature is normalized to [0, 1] via a sigmoid or min-max transform to ensure
consistent scale across all model inputs.

Feature index mapping:
  0: amount_log          — log10(|amount|+1), normalized
  1: is_round_number     — 1.0 if amount % 1000 == 0 else 0.0
  2: day_of_week_sin     — sin(2π * day_of_week / 7) (cyclical encoding)
  3: day_of_week_cos     — cos(2π * day_of_week / 7) (cyclical encoding)
  4: hour_of_day_sin     — sin(2π * hour / 24) (cyclical encoding)
  5: hour_of_day_cos     — cos(2π * hour / 24) (cyclical encoding)
  6: is_outside_hours    — 1.0 if hour < 7 or hour > 19 else 0.0
  7: is_weekend          — 1.0 if day_of_week in {5, 6} else 0.0
  8: vendor_age_norm     — sigmoid((vendor_age_days - 365) / 365) — sigmoid-normalized
  9: account_interaction_freq — percentile rank of this account pair's frequency [0,1]
  10: jurisdictional_risk — pre-computed risk score [0,1] from jurisdiction_risk_scores table
  11: velocity_z_score   — sigmoid(transaction_velocity_zscore) — normalized z-score
"""

import math
import numpy as np
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class FeatureContext:
    """Contextual data required to compute features for a single transaction."""
    amount: float
    timestamp_utc: datetime
    vendor_age_days: float                    # Days since first transaction with this vendor
    account_interaction_percentile: float     # [0, 1] — how rare is this account pair
    jurisdictional_risk: float                # [0, 1] — from jurisdiction_risk_scores
    transaction_velocity_zscore: float        # Z-score of tx count vs. trailing 12-week mean

    # Optional — used when available
    entity_id: str = ""
    entity_type: str = "transaction"
    source_system: str = ""


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def extract_features(ctx: FeatureContext) -> np.ndarray:
    """
    Extracts the 12-dimensional normalized feature vector.

    All features are in [0, 1] after normalization.
    Uses cyclical encoding for time features to preserve periodicity
    (e.g. Sunday and Monday are close in the feature space).
    """
    amount = abs(ctx.amount)
    ts = ctx.timestamp_utc

    # Ensure timezone-aware
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    day_of_week = ts.weekday()   # 0=Monday, 6=Sunday
    hour_of_day = ts.hour

    # Feature 0: log-compressed amount (handles orders of magnitude variation)
    amount_log = math.log10(amount + 1)
    amount_log_norm = sigmoid((amount_log - 4.0) / 2.0)  # center around 10,000

    # Feature 1: round number flag
    is_round_number = 1.0 if (amount > 0 and amount % 1000 == 0) else 0.0

    # Features 2-3: cyclical day-of-week encoding
    day_angle = 2 * math.pi * day_of_week / 7
    day_sin = (math.sin(day_angle) + 1) / 2  # normalize to [0, 1]
    day_cos = (math.cos(day_angle) + 1) / 2

    # Features 4-5: cyclical hour-of-day encoding
    hour_angle = 2 * math.pi * hour_of_day / 24
    hour_sin = (math.sin(hour_angle) + 1) / 2
    hour_cos = (math.cos(hour_angle) + 1) / 2

    # Feature 6: outside business hours flag
    is_outside_hours = 1.0 if (hour_of_day < 7 or hour_of_day > 19) else 0.0

    # Feature 7: weekend flag
    is_weekend = 1.0 if day_of_week >= 5 else 0.0

    # Feature 8: vendor age (sigmoid-normalized around 1 year)
    vendor_age_norm = sigmoid((ctx.vendor_age_days - 365) / 365)

    # Feature 9: account interaction frequency percentile
    account_freq = float(np.clip(ctx.account_interaction_percentile, 0.0, 1.0))

    # Feature 10: jurisdictional risk
    juris_risk = float(np.clip(ctx.jurisdictional_risk, 0.0, 1.0))

    # Feature 11: transaction velocity z-score (sigmoid-normalized)
    velocity_norm = sigmoid(ctx.transaction_velocity_zscore / 3.0)

    features = np.array([
        amount_log_norm,      # 0
        is_round_number,      # 1
        day_sin,              # 2
        day_cos,              # 3
        hour_sin,             # 4
        hour_cos,             # 5
        is_outside_hours,     # 6
        is_weekend,           # 7
        vendor_age_norm,      # 8
        account_freq,         # 9
        juris_risk,           # 10
        velocity_norm,        # 11
    ], dtype=np.float32)

    assert features.shape == (12,), f"Expected 12 features, got {features.shape}"
    assert np.all(features >= 0) and np.all(features <= 1), \
        f"Features out of [0,1] range: {features}"

    return features


def build_feature_context_from_canonical(
    canonical_payload: dict,
    vendor_age_days: float = 365.0,
    account_interaction_percentile: float = 0.5,
    jurisdictional_risk: float = 0.1,
    transaction_velocity_zscore: float = 0.0,
) -> FeatureContext:
    """
    Builds a FeatureContext from a canonical evidence record payload.
    Context fields (vendor_age_days, etc.) must be supplied by the caller
    — they come from the DB enrichment step in features_enricher.py.
    """
    amount = float(canonical_payload.get('metadata', {}).get('amount', 0.0))

    ts_str = canonical_payload.get('timestamp_utc', '')
    try:
        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        ts = datetime.now(timezone.utc)

    return FeatureContext(
        amount=amount,
        timestamp_utc=ts,
        vendor_age_days=vendor_age_days,
        account_interaction_percentile=account_interaction_percentile,
        jurisdictional_risk=jurisdictional_risk,
        transaction_velocity_zscore=transaction_velocity_zscore,
        entity_id=canonical_payload.get('entity_id', ''),
        entity_type=canonical_payload.get('entity_type', 'transaction'),
        source_system=canonical_payload.get('source_system', ''),
    )


class FeatureBatch:
    """
    Batch feature extractor — converts a list of FeatureContexts into a
    numpy matrix of shape (N, 12) suitable for batch inference.
    """

    def __init__(self, contexts: list[FeatureContext]):
        self.contexts = contexts

    def to_matrix(self) -> np.ndarray:
        """
        Returns a float32 numpy array of shape (N, 12).
        Each row is the normalized feature vector for the corresponding context.
        """
        if not self.contexts:
            return np.empty((0, 12), dtype=np.float32)
        rows = [extract_features(ctx) for ctx in self.contexts]
        matrix = np.stack(rows, axis=0)
        assert matrix.shape == (len(self.contexts), 12), \
            f"Expected ({len(self.contexts)}, 12), got {matrix.shape}"
        return matrix

    def __len__(self) -> int:
        return len(self.contexts)
