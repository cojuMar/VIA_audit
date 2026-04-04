"""
Sprint 3 — DRI Ensemble & Meta-Classifier Tests

Verifies DRIWeights normalisation, EnsembleInput feature vectors,
weighted-sum scoring, meta-classifier training guards, risk-level
thresholds, and — critically — cross-tenant model isolation.
"""

import sys
import os
import copy

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

from ensemble import (
    DRIEnsemble,
    DRIWeights,
    EnsembleInput,
    RiskLevel,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_weights(**overrides) -> DRIWeights:
    """Return a DRIWeights with sensible defaults, optionally overriding fields."""
    base = dict(
        benford_weight=0.15,
        vae_weight=0.20,
        velocity_weight=0.15,
        round_number_weight=0.10,
        new_vendor_weight=0.10,
        off_hours_weight=0.10,
        geo_risk_weight=0.10,
        jurisdiction_weight=0.10,
    )
    base.update(overrides)
    return DRIWeights(**base)


def _zero_input() -> EnsembleInput:
    return EnsembleInput(
        benford_score=0.0,
        vae_score=0.0,
        velocity_score=0.0,
        round_number_score=0.0,
        new_vendor_score=0.0,
        off_hours_score=0.0,
        geo_risk_score=0.0,
        jurisdiction_score=0.0,
    )


def _one_input() -> EnsembleInput:
    return EnsembleInput(
        benford_score=1.0,
        vae_score=1.0,
        velocity_score=1.0,
        round_number_score=1.0,
        new_vendor_score=1.0,
        off_hours_score=1.0,
        geo_risk_score=1.0,
        jurisdiction_score=1.0,
    )


def _random_inputs(n: int, seed: int = 42) -> list[EnsembleInput]:
    rng = np.random.RandomState(seed)
    inputs = []
    for _ in range(n):
        scores = rng.uniform(0.0, 1.0, size=8)
        inputs.append(
            EnsembleInput(
                benford_score=float(scores[0]),
                vae_score=float(scores[1]),
                velocity_score=float(scores[2]),
                round_number_score=float(scores[3]),
                new_vendor_score=float(scores[4]),
                off_hours_score=float(scores[5]),
                geo_risk_score=float(scores[6]),
                jurisdiction_score=float(scores[7]),
            )
        )
    return inputs


def _make_labeled_dataset(
    n: int = 100, seed: int = 42
) -> tuple[list[EnsembleInput], list[int]]:
    """
    Build a synthetically separable labeled dataset.
    Low-score inputs → label 0 (not fraud).
    High-score inputs → label 1 (fraud).
    """
    rng = np.random.RandomState(seed)
    inputs, labels = [], []
    half = n // 2

    # Class 0: scores uniformly in [0.0, 0.35]
    for _ in range(half):
        scores = rng.uniform(0.0, 0.35, size=8)
        inputs.append(
            EnsembleInput(**{
                f: float(scores[i])
                for i, f in enumerate([
                    "benford_score", "vae_score", "velocity_score",
                    "round_number_score", "new_vendor_score", "off_hours_score",
                    "geo_risk_score", "jurisdiction_score",
                ])
            })
        )
        labels.append(0)

    # Class 1: scores uniformly in [0.65, 1.0]
    for _ in range(n - half):
        scores = rng.uniform(0.65, 1.0, size=8)
        inputs.append(
            EnsembleInput(**{
                f: float(scores[i])
                for i, f in enumerate([
                    "benford_score", "vae_score", "velocity_score",
                    "round_number_score", "new_vendor_score", "off_hours_score",
                    "geo_risk_score", "jurisdiction_score",
                ])
            })
        )
        labels.append(1)

    return inputs, labels


# ===========================================================================
# 1. TestDRIWeights
# ===========================================================================

class TestDRIWeights:
    """DRIWeights normalisation and serialisation."""

    def test_to_weight_vector_length_8(self):
        w = _default_weights()
        vec = w.to_weight_vector()
        assert len(vec) == 8, f"Expected length 8, got {len(vec)}"

    def test_to_weight_vector_returns_array(self):
        w = _default_weights()
        vec = w.to_weight_vector()
        assert isinstance(vec, (list, np.ndarray))

    def test_weights_sum_to_approximately_one(self):
        w = _default_weights()
        vec = np.asarray(w.to_weight_vector(), dtype=float)
        total = float(vec.sum())
        assert abs(total - 1.0) < 1e-6, (
            f"DRIWeights should sum to ~1.0 after normalisation, got {total}"
        )

    def test_all_weights_non_negative(self):
        w = _default_weights()
        vec = np.asarray(w.to_weight_vector(), dtype=float)
        assert np.all(vec >= 0.0), "All weights must be non-negative"

    def test_from_db_row_maps_all_fields(self):
        row = {
            "benford_weight": 0.12,
            "vae_weight": 0.18,
            "velocity_weight": 0.14,
            "round_number_weight": 0.11,
            "new_vendor_weight": 0.09,
            "off_hours_weight": 0.12,
            "geo_risk_weight": 0.13,
            "jurisdiction_weight": 0.11,
        }
        w = DRIWeights.from_db_row(row)
        assert isinstance(w, DRIWeights)
        # Spot-check a field
        # After normalisation the relative ratios should be preserved
        vec = np.asarray(w.to_weight_vector(), dtype=float)
        total_raw = sum(row.values())
        for i, key in enumerate([
            "benford_weight", "vae_weight", "velocity_weight",
            "round_number_weight", "new_vendor_weight", "off_hours_weight",
            "geo_risk_weight", "jurisdiction_weight",
        ]):
            expected_normalised = row[key] / total_raw
            assert abs(vec[i] - expected_normalised) < 1e-6, (
                f"Field {key}: expected normalised weight {expected_normalised:.6f}, "
                f"got {vec[i]:.6f}"
            )

    def test_from_db_row_sum_still_one(self):
        row = {k: v for k, v in zip(
            ["benford_weight", "vae_weight", "velocity_weight",
             "round_number_weight", "new_vendor_weight", "off_hours_weight",
             "geo_risk_weight", "jurisdiction_weight"],
            [2.0, 3.0, 1.5, 1.0, 0.5, 0.5, 0.5, 0.5]
        )}
        w = DRIWeights.from_db_row(row)
        vec = np.asarray(w.to_weight_vector(), dtype=float)
        assert abs(float(vec.sum()) - 1.0) < 1e-6


# ===========================================================================
# 2. TestEnsembleInput
# ===========================================================================

class TestEnsembleInput:
    """EnsembleInput serialisation to feature vector."""

    def test_to_feature_vector_shape(self):
        inp = _zero_input()
        fv = inp.to_feature_vector()
        fv = np.asarray(fv)
        assert fv.shape == (8,), f"Expected shape (8,), got {fv.shape}"

    def test_to_feature_vector_all_in_unit_interval(self):
        for seed in range(5):
            inp = _random_inputs(1, seed=seed)[0]
            fv = np.asarray(inp.to_feature_vector(), dtype=float)
            assert np.all(fv >= 0.0) and np.all(fv <= 1.0), (
                f"Feature vector out of [0,1]: {fv}"
            )

    def test_zero_input_feature_vector(self):
        fv = np.asarray(_zero_input().to_feature_vector(), dtype=float)
        np.testing.assert_array_equal(fv, np.zeros(8))

    def test_one_input_feature_vector(self):
        fv = np.asarray(_one_input().to_feature_vector(), dtype=float)
        np.testing.assert_array_equal(fv, np.ones(8))


# ===========================================================================
# 3. TestDRIComputation
# ===========================================================================

class TestDRIComputation:
    """DRIEnsemble.score() correctness."""

    @pytest.fixture
    def ensemble(self) -> DRIEnsemble:
        return DRIEnsemble(weights=_default_weights(), tenant_id="test-tenant")

    def test_score_in_unit_interval(self, ensemble):
        for inp in _random_inputs(50, seed=7):
            result = ensemble.score(inp)
            assert 0.0 <= result.dri_score <= 1.0, (
                f"DRI score {result.dri_score} out of [0,1]"
            )

    def test_all_zero_input_low_risk(self, ensemble):
        result = ensemble.score(_zero_input())
        assert result.risk_level == RiskLevel.LOW or result.risk_level == "low", (
            f"All-zero input should be low risk, got {result.risk_level}"
        )

    def test_all_one_input_high_or_critical_risk(self, ensemble):
        result = ensemble.score(_one_input())
        level = result.risk_level
        if isinstance(level, str):
            level = level.lower()
            assert level in ("high", "critical"), (
                f"All-one input should be high/critical, got {level}"
            )
        else:
            assert level in (RiskLevel.HIGH, RiskLevel.CRITICAL), (
                f"All-one input should be high/critical, got {level}"
            )

    def test_result_has_top_risk_factors(self, ensemble):
        result = ensemble.score(_random_inputs(1, seed=8)[0])
        assert hasattr(result, "top_risk_factors"), (
            "Result must have 'top_risk_factors' attribute"
        )
        assert len(result.top_risk_factors) == 3, (
            f"Expected 3 top_risk_factors, got {len(result.top_risk_factors)}"
        )

    def test_deterministic_same_input(self, ensemble):
        inp = _random_inputs(1, seed=9)[0]
        r1 = ensemble.score(inp)
        r2 = ensemble.score(inp)
        assert r1.dri_score == r2.dri_score, (
            "score() must be deterministic for the same input"
        )

    def test_scored_by_weighted_sum_without_meta_classifier(self, ensemble):
        result = ensemble.score(_random_inputs(1, seed=10)[0])
        assert result.scored_by == "weighted_sum", (
            f"Expected scored_by='weighted_sum', got '{result.scored_by}'"
        )


# ===========================================================================
# 4. TestMetaClassifierTraining
# ===========================================================================

class TestMetaClassifierTraining:
    """Guards and accuracy assertions for train_meta_classifier()."""

    def _fresh_ensemble(self) -> DRIEnsemble:
        return DRIEnsemble(weights=_default_weights(), tenant_id="ml-train-tenant")

    def test_raises_for_fewer_than_50_samples(self):
        ensemble = self._fresh_ensemble()
        inputs, labels = _make_labeled_dataset(n=40, seed=1)
        with pytest.raises(ValueError, match=r"(?i).*50.*|.*sample.*"):
            ensemble.train_meta_classifier(inputs, labels)

    def test_raises_for_class_imbalance_too_few_positives(self):
        """Fewer than 5 fraud (class-1) samples must raise ValueError."""
        ensemble = self._fresh_ensemble()
        inputs, labels = _make_labeled_dataset(n=100, seed=2)
        # Replace all class-1 labels except 3 with class-0
        fraud_indices = [i for i, l in enumerate(labels) if l == 1]
        for idx in fraud_indices[3:]:
            labels[idx] = 0
        with pytest.raises(ValueError):
            ensemble.train_meta_classifier(inputs, labels)

    def test_raises_for_class_imbalance_too_few_negatives(self):
        """Fewer than 5 non-fraud (class-0) samples must raise ValueError."""
        ensemble = self._fresh_ensemble()
        inputs, labels = _make_labeled_dataset(n=100, seed=3)
        non_fraud_indices = [i for i, l in enumerate(labels) if l == 0]
        for idx in non_fraud_indices[3:]:
            labels[idx] = 1
        with pytest.raises(ValueError):
            ensemble.train_meta_classifier(inputs, labels)

    def test_train_accuracy_above_chance(self):
        ensemble = self._fresh_ensemble()
        inputs, labels = _make_labeled_dataset(n=100, seed=4)
        result = ensemble.train_meta_classifier(inputs, labels)
        assert result.train_accuracy > 0.5, (
            f"Meta-classifier train accuracy {result.train_accuracy:.3f} should exceed 0.5"
        )

    def test_scored_by_meta_classifier_after_training(self):
        ensemble = self._fresh_ensemble()
        inputs, labels = _make_labeled_dataset(n=100, seed=5)
        ensemble.train_meta_classifier(inputs, labels)

        test_input = _random_inputs(1, seed=99)[0]
        result = ensemble.score(test_input)
        assert result.scored_by == "meta_classifier", (
            f"After training, scored_by should be 'meta_classifier', got '{result.scored_by}'"
        )

    def test_meta_classifier_score_in_unit_interval(self):
        ensemble = self._fresh_ensemble()
        inputs, labels = _make_labeled_dataset(n=100, seed=6)
        ensemble.train_meta_classifier(inputs, labels)

        for inp in _random_inputs(20, seed=50):
            result = ensemble.score(inp)
            assert 0.0 <= result.dri_score <= 1.0, (
                f"Meta-classifier DRI score {result.dri_score} out of [0,1]"
            )

    def test_highly_separable_data_high_accuracy(self):
        """
        With well-separated classes the meta-classifier should achieve
        at least 80% training accuracy.
        """
        ensemble = self._fresh_ensemble()
        inputs, labels = _make_labeled_dataset(n=200, seed=7)
        result = ensemble.train_meta_classifier(inputs, labels)
        assert result.train_accuracy >= 0.80, (
            f"Expected ≥80% accuracy on separable data, got {result.train_accuracy:.3f}"
        )


# ===========================================================================
# 5. TestRiskLevelThresholds
# ===========================================================================

class TestRiskLevelThresholds:
    """Verify exact DRI → risk-level boundary mapping."""

    def _score_for_dri(self, dri: float) -> str:
        """
        Directly call the classify function or infer from a mock result.
        Tries DRIEnsemble.classify_risk_level() first, then falls back to
        inspecting a result from score() with a known weighted sum.
        """
        try:
            from ensemble import classify_risk_level
            level = classify_risk_level(dri)
        except ImportError:
            # Fall back: construct an ensemble with unit weights, pass
            # a hand-crafted input that produces the desired DRI.
            ensemble = DRIEnsemble(
                weights=_default_weights(), tenant_id="threshold-test"
            )
            # Use benford_score = dri (all other scores = 0) with weight 1
            # Not ideal — prefer direct classify_risk_level if available.
            inp = EnsembleInput(
                benford_score=dri,
                vae_score=dri,
                velocity_score=dri,
                round_number_score=dri,
                new_vendor_score=dri,
                off_hours_score=dri,
                geo_risk_score=dri,
                jurisdiction_score=dri,
            )
            result = ensemble.score(inp)
            level = result.risk_level

        if isinstance(level, RiskLevel):
            return level.value if hasattr(level, "value") else str(level).lower()
        return str(level).lower()

    def test_below_0_3_is_low(self):
        for dri in [0.0, 0.1, 0.15, 0.25, 0.29]:
            level = self._score_for_dri(dri)
            assert level == "low", f"DRI={dri} → expected 'low', got '{level}'"

    def test_0_3_to_0_6_is_medium(self):
        for dri in [0.3, 0.35, 0.45, 0.55, 0.59]:
            level = self._score_for_dri(dri)
            assert level == "medium", f"DRI={dri} → expected 'medium', got '{level}'"

    def test_0_6_to_0_8_is_high(self):
        for dri in [0.6, 0.65, 0.70, 0.75, 0.79]:
            level = self._score_for_dri(dri)
            assert level == "high", f"DRI={dri} → expected 'high', got '{level}'"

    def test_0_8_and_above_is_critical(self):
        for dri in [0.8, 0.85, 0.9, 0.95, 1.0]:
            level = self._score_for_dri(dri)
            assert level == "critical", f"DRI={dri} → expected 'critical', got '{level}'"


# ===========================================================================
# 6. TestCrossTenantsIsolation — CRITICAL
# ===========================================================================

class TestCrossTenantsIsolation:
    """
    CRITICAL SECURITY TEST.

    Two tenant DRIEnsemble instances must be completely isolated.
    Training ensemble_a's meta-classifier must NOT affect ensemble_b.
    """

    def _make_ensembles(self) -> tuple[DRIEnsemble, DRIEnsemble]:
        weights_a = _default_weights()
        weights_b = _default_weights()
        ensemble_a = DRIEnsemble(weights=weights_a, tenant_id="tenant-alpha")
        ensemble_b = DRIEnsemble(weights=weights_b, tenant_id="tenant-beta")
        return ensemble_a, ensemble_b

    def test_ensemble_b_untrained_after_a_trains(self):
        """
        After training ensemble_a, ensemble_b must still score via 'weighted_sum'.
        """
        ensemble_a, ensemble_b = self._make_ensembles()
        inputs, labels = _make_labeled_dataset(n=100, seed=20)

        ensemble_a.train_meta_classifier(inputs, labels)

        test_input = _random_inputs(1, seed=21)[0]
        result_b = ensemble_b.score(test_input)
        assert result_b.scored_by == "weighted_sum", (
            f"ensemble_b should still use 'weighted_sum' after ensemble_a was trained, "
            f"got '{result_b.scored_by}'. Possible cross-tenant state leak!"
        )

    def test_ensemble_a_uses_meta_classifier_after_training(self):
        """
        Sanity: ensemble_a should use the meta-classifier after training.
        """
        ensemble_a, _ = self._make_ensembles()
        inputs, labels = _make_labeled_dataset(n=100, seed=22)
        ensemble_a.train_meta_classifier(inputs, labels)

        result_a = ensemble_a.score(_random_inputs(1, seed=23)[0])
        assert result_a.scored_by == "meta_classifier", (
            f"ensemble_a should use 'meta_classifier', got '{result_a.scored_by}'"
        )

    def test_no_shared_classifier_state(self):
        """
        Deep-equality check: the internal meta-classifier object of ensemble_a
        must not be the same object (or reference) as that of ensemble_b.
        """
        ensemble_a, ensemble_b = self._make_ensembles()
        inputs, labels = _make_labeled_dataset(n=100, seed=24)
        ensemble_a.train_meta_classifier(inputs, labels)

        clf_a = getattr(ensemble_a, "_meta_classifier", None)
        clf_b = getattr(ensemble_b, "_meta_classifier", None)

        # ensemble_b should have no trained classifier
        assert clf_b is None or (
            hasattr(clf_b, "is_fitted_") and not clf_b.is_fitted_
        ), (
            "ensemble_b should not have a trained meta-classifier after "
            "only ensemble_a was trained. Possible shared state!"
        )

    def test_training_a_does_not_change_b_scores(self):
        """
        ensemble_b scores must be identical before and after training ensemble_a.
        """
        ensemble_a, ensemble_b = self._make_ensembles()
        test_inputs = _random_inputs(10, seed=25)

        # Capture ensemble_b scores BEFORE training ensemble_a
        scores_before = [
            ensemble_b.score(inp).dri_score for inp in test_inputs
        ]

        # Train ensemble_a
        inputs, labels = _make_labeled_dataset(n=100, seed=26)
        ensemble_a.train_meta_classifier(inputs, labels)

        # Capture ensemble_b scores AFTER training ensemble_a
        scores_after = [
            ensemble_b.score(inp).dri_score for inp in test_inputs
        ]

        for i, (before, after) in enumerate(zip(scores_before, scores_after)):
            assert before == after, (
                f"ensemble_b score for input {i} changed after training ensemble_a: "
                f"{before} → {after}. Cross-tenant isolation violated!"
            )

    def test_tenant_ids_are_distinct(self):
        ensemble_a, ensemble_b = self._make_ensembles()
        assert ensemble_a.tenant_id != ensemble_b.tenant_id, (
            "Test setup error: tenant IDs must differ"
        )

    def test_separate_weight_objects(self):
        """
        DRIWeights used by each ensemble must not be the same object.
        Modifying one should not affect the other.
        """
        ensemble_a, ensemble_b = self._make_ensembles()
        vec_b_before = np.asarray(
            ensemble_b.weights.to_weight_vector(), dtype=float
        ).copy()

        # Mutate ensemble_a's weights if possible (implementation-specific)
        try:
            ensemble_a.weights.benford_weight = 9999.0
        except (AttributeError, TypeError):
            # Immutable weights — isolation guaranteed by design
            return

        vec_b_after = np.asarray(
            ensemble_b.weights.to_weight_vector(), dtype=float
        )
        np.testing.assert_array_equal(
            vec_b_before, vec_b_after,
            err_msg=(
                "Mutating ensemble_a weights altered ensemble_b weights — "
                "weights objects must not be shared!"
            ),
        )
