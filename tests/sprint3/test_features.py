"""
Sprint 3 — Feature Extraction Tests

Verifies the 12-dimensional feature vector produced by extract_features(),
cyclical time encodings, amount log-normalisation, and batch assembly.
"""

import math
import sys
import os
from datetime import datetime, timezone

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__), "..", "..", "services", "forensic-ml-service", "src"
    ),
)

from features import FeatureContext, extract_features, extract_features_batch

# ---------------------------------------------------------------------------
# Helpers — canonical FeatureContext factories
# ---------------------------------------------------------------------------

def _ctx(
    amount: float = 500.0,
    timestamp: datetime | None = None,
    vendor_tx_count: int = 10,
    vendor_avg_amount: float = 300.0,
    account_tx_count: int = 20,
    account_avg_amount: float = 400.0,
    days_since_last_tx: float = 3.0,
    is_new_vendor: bool = False,
) -> FeatureContext:
    if timestamp is None:
        # Wednesday 10:30 — a normal mid-week business hour
        timestamp = datetime(2026, 3, 18, 10, 30, 0, tzinfo=timezone.utc)
    return FeatureContext(
        amount=amount,
        timestamp=timestamp,
        vendor_tx_count=vendor_tx_count,
        vendor_avg_amount=vendor_avg_amount,
        account_tx_count=account_tx_count,
        account_avg_amount=account_avg_amount,
        days_since_last_tx=days_since_last_tx,
        is_new_vendor=is_new_vendor,
    )


def _ctx_at_hour(hour: int, weekday_override: int | None = None) -> FeatureContext:
    """
    Return a FeatureContext whose timestamp has the given hour (UTC).
    weekday_override: 0=Monday … 6=Sunday; if None a weekday is used.
    """
    # Find a date with the right weekday
    if weekday_override is not None:
        # 2026-03-16 is a Monday (weekday=0)
        base = datetime(2026, 3, 16, tzinfo=timezone.utc)
        delta_days = (weekday_override - base.weekday()) % 7
        from datetime import timedelta
        target_date = base + timedelta(days=delta_days)
        ts = target_date.replace(hour=hour, minute=0, second=0)
    else:
        ts = datetime(2026, 3, 18, hour, 0, 0, tzinfo=timezone.utc)  # Wednesday
    return _ctx(timestamp=ts)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

FEATURE_DIM = 12


def _vec(ctx: FeatureContext) -> np.ndarray:
    return extract_features(ctx)


# ===========================================================================
# 1. TestFeatureVector
# ===========================================================================

class TestFeatureVector:
    """Basic shape, range, and determinism guarantees."""

    def test_returns_ndarray(self):
        v = _vec(_ctx())
        assert isinstance(v, np.ndarray)

    def test_shape_is_12(self):
        v = _vec(_ctx())
        assert v.shape == (FEATURE_DIM,), f"Expected shape ({FEATURE_DIM},), got {v.shape}"

    def test_all_values_in_unit_interval(self):
        v = _vec(_ctx())
        assert np.all(v >= 0.0) and np.all(v <= 1.0), (
            f"Some features outside [0,1]: {v}"
        )

    def test_deterministic(self):
        ctx = _ctx(amount=1234.0)
        v1 = _vec(ctx)
        v2 = _vec(ctx)
        np.testing.assert_array_equal(v1, v2)

    def test_weekend_saturday_flag(self):
        # 2026-03-21 is a Saturday (weekday=5)
        ts = datetime(2026, 3, 21, 14, 0, 0, tzinfo=timezone.utc)
        ctx = _ctx(timestamp=ts)
        v = _vec(ctx)
        # Locate the is_weekend feature by checking the documented index or by
        # inspecting a feature named 'is_weekend'.
        assert hasattr(extract_features, "__doc__") or True  # import check
        fe = _feature_by_name_or_assert(ctx, "is_weekend")
        assert fe == 1.0, f"Saturday should have is_weekend=1.0, got {fe}"

    def test_weekday_monday_no_weekend_flag(self):
        ts = datetime(2026, 3, 16, 9, 0, 0, tzinfo=timezone.utc)  # Monday
        ctx = _ctx(timestamp=ts)
        fe = _feature_by_name_or_assert(ctx, "is_weekend")
        assert fe == 0.0, f"Monday should have is_weekend=0.0, got {fe}"

    def test_hour_3am_is_outside_hours(self):
        ctx = _ctx_at_hour(3)
        fe = _feature_by_name_or_assert(ctx, "is_outside_hours")
        assert fe == 1.0, f"3am should be outside business hours, got {fe}"

    def test_hour_10am_not_outside_hours(self):
        ctx = _ctx_at_hour(10)
        fe = _feature_by_name_or_assert(ctx, "is_outside_hours")
        assert fe == 0.0, f"10am should be inside business hours, got {fe}"


def _feature_by_name_or_assert(ctx: FeatureContext, name: str) -> float:
    """
    Try to get a named feature from the feature module.
    If the module exposes a feature-name mapping, use it.
    Otherwise fall back to extract_features_named() if available,
    or raise a clear error so the implementor knows what's needed.
    """
    # Prefer a dictionary API if the module exposes it
    try:
        from features import extract_features_named
        d = extract_features_named(ctx)
        return float(d[name])
    except (ImportError, AttributeError, TypeError):
        pass

    # Fall back to a FEATURE_NAMES constant
    try:
        from features import FEATURE_NAMES
        v = extract_features(ctx)
        idx = FEATURE_NAMES.index(name)
        return float(v[idx])
    except (ImportError, AttributeError, ValueError):
        pass

    pytest.fail(
        f"Cannot locate feature '{name}'. "
        "The features module must expose either FEATURE_NAMES (list) "
        "or extract_features_named() returning a dict."
    )


# ===========================================================================
# 2. TestCyclicalTimeEncoding
# ===========================================================================

class TestCyclicalTimeEncoding:
    """
    Cyclical encodings must preserve circular distance:
    - Sunday and Monday are adjacent on the week cycle.
    - Hour 23 and hour 0 are adjacent on the hour cycle.
    """

    def _day_vec(self, weekday: int) -> np.ndarray:
        return _vec(_ctx_at_hour(12, weekday_override=weekday))

    def _hour_vec(self, hour: int) -> np.ndarray:
        return _vec(_ctx_at_hour(hour))

    def _cyclical_dist(self, v1: np.ndarray, v2: np.ndarray) -> float:
        """Euclidean distance — used as a proxy for closeness in feature space."""
        return float(np.linalg.norm(v1 - v2))

    def test_sunday_monday_close_in_feature_space(self):
        """
        Sunday (6) and Monday (0) are only 1 day apart cyclically.
        They should be closer than Monday (0) and Thursday (3).
        """
        v_sun = self._day_vec(6)   # Sunday
        v_mon = self._day_vec(0)   # Monday
        v_thu = self._day_vec(3)   # Thursday

        dist_sun_mon = self._cyclical_dist(v_sun, v_mon)
        dist_mon_thu = self._cyclical_dist(v_mon, v_thu)

        assert dist_sun_mon < dist_mon_thu, (
            f"Sunday↔Monday dist ({dist_sun_mon:.4f}) should be < "
            f"Monday↔Thursday dist ({dist_mon_thu:.4f})"
        )

    def test_hour_23_and_hour_0_close(self):
        """
        Hour 23 and hour 0 are adjacent cyclically.
        They should be closer than hour 0 and hour 12.
        """
        v_23 = self._hour_vec(23)
        v_0 = self._hour_vec(0)
        v_12 = self._hour_vec(12)

        dist_23_0 = self._cyclical_dist(v_23, v_0)
        dist_0_12 = self._cyclical_dist(v_0, v_12)

        assert dist_23_0 < dist_0_12, (
            f"Hour-23↔Hour-0 dist ({dist_23_0:.4f}) should be < "
            f"Hour-0↔Hour-12 dist ({dist_0_12:.4f})"
        )

    def test_cyclical_encoding_uses_sin_cos(self):
        """
        Smoke test: the sin and cos of day-of-week for Monday (0) and
        Saturday (5) should be distinct from each other.
        """
        v_mon = self._day_vec(0)
        v_sat = self._day_vec(5)
        assert not np.allclose(v_mon, v_sat), (
            "Monday and Saturday should have different feature vectors"
        )


# ===========================================================================
# 3. TestAmountLogNormalization
# ===========================================================================

class TestAmountLogNormalization:
    """Tests for amount normalisation and round-number detection."""

    def test_zero_amount_near_zero_not_nan(self):
        ctx = _ctx(amount=0.0)
        v = _vec(ctx)
        assert not np.any(np.isnan(v)), "Zero amount must not produce NaN"
        assert not np.any(np.isinf(v)), "Zero amount must not produce inf"
        # The amount feature itself should be near zero (not a large value)
        amt_feature = _feature_by_name_or_assert(ctx, "amount_norm")
        assert amt_feature >= 0.0
        assert amt_feature < 0.2, f"Zero amount normalised to {amt_feature}, expected near 0"

    def test_large_amount_high_normalised_value(self):
        ctx = _ctx(amount=1_000_000.0)
        amt_feature = _feature_by_name_or_assert(ctx, "amount_norm")
        assert 0.8 <= amt_feature <= 1.0, (
            f"1M amount normalised to {amt_feature}, expected [0.8, 1.0]"
        )

    def test_unit_amount_small_normalised_value(self):
        ctx = _ctx(amount=1.0)
        amt_feature = _feature_by_name_or_assert(ctx, "amount_norm")
        assert amt_feature >= 0.0
        assert amt_feature < 0.3, (
            f"Amount=1 normalised to {amt_feature}, expected small positive"
        )

    def test_round_number_flag_true(self):
        ctx = _ctx(amount=10_000.0)
        fe = _feature_by_name_or_assert(ctx, "is_round_number")
        assert fe == 1.0, f"10000 should be flagged as round, got {fe}"

    def test_non_round_number_flag_false(self):
        ctx = _ctx(amount=10_001.0)
        fe = _feature_by_name_or_assert(ctx, "is_round_number")
        assert fe == 0.0, f"10001 should NOT be flagged as round, got {fe}"

    def test_round_number_100(self):
        ctx = _ctx(amount=100.0)
        fe = _feature_by_name_or_assert(ctx, "is_round_number")
        assert fe == 1.0

    def test_round_number_5000(self):
        ctx = _ctx(amount=5000.0)
        fe = _feature_by_name_or_assert(ctx, "is_round_number")
        assert fe == 1.0

    def test_non_round_small(self):
        ctx = _ctx(amount=99.99)
        fe = _feature_by_name_or_assert(ctx, "is_round_number")
        assert fe == 0.0

    def test_amount_norm_monotone(self):
        """Larger amounts should produce larger (or equal) normalised values."""
        amounts = [1.0, 100.0, 1_000.0, 10_000.0, 100_000.0, 1_000_000.0]
        norms = [
            _feature_by_name_or_assert(_ctx(amount=a), "amount_norm")
            for a in amounts
        ]
        for i in range(len(norms) - 1):
            assert norms[i] <= norms[i + 1], (
                f"amount_norm not monotone: {amounts[i]}→{norms[i]:.4f} "
                f"> {amounts[i+1]}→{norms[i+1]:.4f}"
            )


# ===========================================================================
# 4. TestFeatureBatch
# ===========================================================================

class TestFeatureBatch:
    """Tests for extract_features_batch()."""

    def _make_batch(self, n: int) -> list[FeatureContext]:
        import random
        rng = random.Random(42)
        contexts = []
        for i in range(n):
            ts = datetime(
                2026,
                rng.randint(1, 12),
                rng.randint(1, 28),
                rng.randint(0, 23),
                rng.randint(0, 59),
                tzinfo=timezone.utc,
            )
            contexts.append(
                FeatureContext(
                    amount=rng.uniform(1.0, 500_000.0),
                    timestamp=ts,
                    vendor_tx_count=rng.randint(1, 200),
                    vendor_avg_amount=rng.uniform(100.0, 50_000.0),
                    account_tx_count=rng.randint(1, 500),
                    account_avg_amount=rng.uniform(100.0, 100_000.0),
                    days_since_last_tx=rng.uniform(0.0, 365.0),
                    is_new_vendor=rng.choice([True, False]),
                )
            )
        return contexts

    def test_batch_shape(self):
        batch = self._make_batch(100)
        matrix = extract_features_batch(batch)
        assert isinstance(matrix, np.ndarray)
        assert matrix.shape == (100, FEATURE_DIM), (
            f"Expected shape (100, {FEATURE_DIM}), got {matrix.shape}"
        )

    def test_batch_all_values_in_unit_interval(self):
        batch = self._make_batch(100)
        matrix = extract_features_batch(batch)
        assert np.all(matrix >= 0.0), "Batch contains negative feature values"
        assert np.all(matrix <= 1.0), "Batch contains feature values > 1.0"

    def test_batch_no_nan_or_inf(self):
        batch = self._make_batch(100)
        matrix = extract_features_batch(batch)
        assert not np.any(np.isnan(matrix)), "Batch contains NaN"
        assert not np.any(np.isinf(matrix)), "Batch contains inf"

    def test_batch_consistent_with_single(self):
        """
        extract_features_batch should return the same values as calling
        extract_features individually for each row.
        """
        batch = self._make_batch(10)
        matrix = extract_features_batch(batch)
        for i, ctx in enumerate(batch):
            single = extract_features(ctx)
            np.testing.assert_array_almost_equal(
                matrix[i], single, decimal=6,
                err_msg=f"Batch row {i} differs from single extract"
            )

    def test_empty_batch_returns_empty_array(self):
        matrix = extract_features_batch([])
        assert isinstance(matrix, np.ndarray)
        assert matrix.shape[0] == 0
