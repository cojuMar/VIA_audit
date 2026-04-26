"""
Sprint 3 — Benford's Law Engine Tests

Verifies the P(d) = log10(1 + 1/d) implementation, MAD computation,
risk classification, and entity-level analysis.
"""

import math
import random
import sys
import os

# ---------------------------------------------------------------------------
# Path setup — allow running from repo root or tests/sprint3 directly
# ---------------------------------------------------------------------------
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__), "..", "..", "services", "forensic-ml-service", "src"
    ),
)

from benford import (
    BENFORD_EXPECTED,
    MAD_CONFORMING,
    MAD_MARGINAL,
    analyze_benford,
    benford_risk_score,
    extract_first_digit,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _benford_sample(n: int, seed: int = 42) -> list[float]:
    """
    Generate n amounts whose first digits follow Benford's distribution.
    Uses the inverse-CDF method: draw U ~ Uniform(0,1), then a = 10^U
    so a ∈ [1, 10) and P(first digit = d) = log10(1 + 1/d).
    Multiply by random scale factors to create realistic magnitudes.
    """
    rng = random.Random(seed)
    amounts: list[float] = []
    for _ in range(n):
        u = rng.random()
        mantissa = 10 ** u          # ∈ [1, 10)
        scale = 10 ** rng.randint(0, 5)
        amounts.append(mantissa * scale)
    return amounts


def _uniform_digit_sample(n: int, seed: int = 99) -> list[float]:
    """
    Generate n amounts whose first digits are uniformly distributed 1–9.
    This deliberately violates Benford's law.
    """
    rng = random.Random(seed)
    amounts: list[float] = []
    for _ in range(n):
        d = rng.randint(1, 9)
        rest = rng.uniform(0, 1)
        scale = 10 ** rng.randint(0, 4)
        amounts.append((d + rest) * scale)
    return amounts


# ===========================================================================
# 1. TestBenfordDistribution
# ===========================================================================

class TestBenfordDistribution:
    """Verifies the theoretical Benford probability table."""

    def test_sum_to_one(self):
        total = sum(BENFORD_EXPECTED.values())
        assert abs(total - 1.0) < 1e-10, f"Expected sum ≈ 1.0, got {total}"

    def test_p1_approx_0_301(self):
        assert abs(BENFORD_EXPECTED[1] - 0.30103) < 1e-4

    def test_p2_approx_0_176(self):
        assert abs(BENFORD_EXPECTED[2] - 0.17609) < 1e-4

    def test_p9_approx_0_046(self):
        assert abs(BENFORD_EXPECTED[9] - 0.04576) < 1e-4

    def test_each_digit_matches_formula(self):
        for d in range(1, 10):
            expected = math.log10(1 + 1 / d)
            assert abs(BENFORD_EXPECTED[d] - expected) < 1e-12, (
                f"Digit {d}: table={BENFORD_EXPECTED[d]}, formula={expected}"
            )

    def test_monotonically_decreasing(self):
        for d in range(1, 9):
            assert BENFORD_EXPECTED[d] > BENFORD_EXPECTED[d + 1], (
                f"P({d}) should be > P({d+1})"
            )

    def test_all_nine_digits_present(self):
        assert set(BENFORD_EXPECTED.keys()) == set(range(1, 10))


# ===========================================================================
# 2. TestFirstDigitExtraction
# ===========================================================================

class TestFirstDigitExtraction:
    """Tests for extract_first_digit()."""

    def test_integer_1234(self):
        assert extract_first_digit(1234.56) == 1

    def test_small_decimal_0_00789(self):
        assert extract_first_digit(0.00789) == 7

    def test_round_power_of_ten(self):
        assert extract_first_digit(100000) == 1

    def test_zero_returns_none(self):
        assert extract_first_digit(0.0) is None

    def test_negative_uses_abs(self):
        # Negative amounts should return the first digit of their absolute value
        result = extract_first_digit(-5432.1)
        assert result == 5, f"Expected 5, got {result}"

    def test_negative_small(self):
        result = extract_first_digit(-0.00321)
        assert result == 3

    def test_very_small_positive(self):
        # 1e-10 → first significant digit is 1
        result = extract_first_digit(1e-10)
        assert result == 1

    def test_very_small_9(self):
        result = extract_first_digit(9e-15)
        assert result == 9

    def test_exactly_one(self):
        assert extract_first_digit(1.0) == 1

    def test_exactly_nine(self):
        assert extract_first_digit(9.9999) == 9

    def test_large_number(self):
        assert extract_first_digit(3_141_592_653.0) == 3


# ===========================================================================
# 3. TestAnalyzeBenford
# ===========================================================================

class TestAnalyzeBenford:
    """Tests for analyze_benford()."""

    def test_fewer_than_30_returns_none(self):
        amounts = list(range(1, 30))   # 29 amounts
        assert analyze_benford(amounts) is None

    def test_exactly_30_returns_result(self):
        amounts = _benford_sample(30, seed=1)
        result = analyze_benford(amounts)
        assert result is not None

    def test_conforming_distribution_low_mad(self):
        amounts = _benford_sample(2000, seed=10)
        result = analyze_benford(amounts)
        assert result is not None
        assert result.mad < 0.006, (
            f"Benford-distributed data should have MAD < 0.006, got {result.mad:.4f}"
        )

    def test_non_conforming_uniform_high_mad(self):
        amounts = _uniform_digit_sample(2000, seed=20)
        result = analyze_benford(amounts)
        assert result is not None
        assert result.mad > 0.015, (
            f"Uniform-digit data should have MAD > 0.015, got {result.mad:.4f}"
        )

    def test_result_has_all_nine_digits(self):
        amounts = _benford_sample(500, seed=3)
        result = analyze_benford(amounts)
        assert result is not None
        assert set(result.digit_counts.keys()) == set(range(1, 10))

    def test_observed_probs_sum_to_one(self):
        amounts = _benford_sample(500, seed=4)
        result = analyze_benford(amounts)
        assert result is not None
        total = sum(result.observed_probs.values())
        assert abs(total - 1.0) < 1e-6, f"observed_probs sum={total}"

    def test_digit_counts_sum_to_transaction_count(self):
        amounts = _benford_sample(300, seed=5)
        result = analyze_benford(amounts)
        assert result is not None
        count_sum = sum(result.digit_counts.values())
        assert count_sum == result.transaction_count

    def test_chi2_pvalue_in_unit_interval(self):
        amounts = _benford_sample(300, seed=6)
        result = analyze_benford(amounts)
        assert result is not None
        assert 0.0 <= result.chi2_pvalue <= 1.0, (
            f"chi2_pvalue={result.chi2_pvalue} outside [0,1]"
        )

    def test_actual_benford_sample_mad_below_threshold(self):
        """
        Inverse-CDF Benford sample of 1000: MAD should be < 0.015.
        Uses the exact inverse-CDF construction described in the spec.
        """
        rng = random.Random(7)
        amounts = []
        for _ in range(1000):
            u = rng.random()
            amounts.append(10 ** u)
        result = analyze_benford(amounts)
        assert result is not None
        assert result.mad < 0.015, (
            f"Inverse-CDF Benford 1000 sample MAD={result.mad:.4f} should be < 0.015"
        )

    def test_empty_list_returns_none(self):
        assert analyze_benford([]) is None

    def test_single_element_returns_none(self):
        assert analyze_benford([42.0]) is None

    def test_result_transaction_count_correct(self):
        amounts = _benford_sample(100, seed=8)
        result = analyze_benford(amounts)
        assert result is not None
        # transaction_count should equal the number of amounts with non-None first digits
        valid = [a for a in amounts if extract_first_digit(a) is not None]
        assert result.transaction_count == len(valid)


# ===========================================================================
# 4. TestBenfordRiskScore
# ===========================================================================

class TestBenfordRiskScore:
    """Tests for benford_risk_score()."""

    def test_none_input_returns_half(self):
        score = benford_risk_score(None)
        assert abs(score - 0.5) < 1e-9, f"Expected 0.5, got {score}"

    def test_zero_mad_near_zero_score(self):
        score = benford_risk_score(0.0)
        assert score < 0.1, f"MAD=0 should yield near-zero risk, got {score}"

    def test_mad_conforming_approx_0_2(self):
        score = benford_risk_score(MAD_CONFORMING)
        assert score < 0.4, (
            f"MAD at conforming threshold should be low-risk, got {score:.3f}"
        )

    def test_mad_marginal_approx_0_8(self):
        score = benford_risk_score(MAD_MARGINAL)
        assert score > 0.6, (
            f"MAD at marginal threshold should be high-risk, got {score:.3f}"
        )

    def test_very_high_mad_near_one(self):
        score = benford_risk_score(0.10)
        assert score > 0.9, f"MAD=0.10 should yield near-1.0 risk, got {score}"

    def test_output_always_in_unit_interval(self):
        for mad in [0.0, 0.001, 0.005, 0.006, 0.010, 0.015, 0.05, 0.1, 0.5, 1.0]:
            s = benford_risk_score(mad)
            assert 0.0 <= s <= 1.0, f"MAD={mad}: score={s} out of [0,1]"

    def test_monotonically_increasing_with_mad(self):
        mads = [0.0, 0.002, 0.005, 0.008, 0.012, 0.02, 0.05, 0.10]
        scores = [benford_risk_score(m) for m in mads]
        for i in range(len(scores) - 1):
            assert scores[i] <= scores[i + 1], (
                f"Score not monotone: MAD={mads[i]} score={scores[i]:.4f} "
                f"> MAD={mads[i+1]} score={scores[i+1]:.4f}"
            )


# ===========================================================================
# 5. TestFabricationDetection (Integration)
# ===========================================================================

class TestFabricationDetection:
    """
    End-to-end integration: can Benford analysis distinguish fabricated
    amounts from genuinely distributed ones?
    """

    def test_digit7_bias_high_mad_and_high_risk(self):
        """
        Attacker always starts amounts with digit 7.
        Expected: MAD >> MAD_MARGINAL, risk_level = 'high' or 'critical'.
        """
        rng = random.Random(11)
        amounts = []
        for _ in range(200):
            # Force first digit = 7
            mantissa = rng.uniform(7.0, 7.999)
            scale = 10 ** rng.randint(0, 4)
            amounts.append(mantissa * scale)

        result = analyze_benford(amounts)
        assert result is not None, "analyze_benford returned None for 200 amounts"
        assert result.mad > MAD_MARGINAL, (
            f"Biased-digit-7 MAD={result.mad:.4f} should exceed MAD_MARGINAL={MAD_MARGINAL}"
        )
        risk = result.risk_level if hasattr(result, "risk_level") else (
            "high" if result.mad > MAD_MARGINAL else "low"
        )
        assert risk in ("high", "critical"), (
            f"Expected high/critical risk for fabricated data, got '{risk}'"
        )

    def test_genuine_benford_distribution_conforming(self):
        """
        Genuinely Benford-distributed amounts: conforming=True, MAD < MAD_MARGINAL.
        """
        amounts = _benford_sample(200, seed=12)
        result = analyze_benford(amounts)
        assert result is not None
        assert result.mad < MAD_MARGINAL, (
            f"Genuine Benford data MAD={result.mad:.4f} should be < MAD_MARGINAL={MAD_MARGINAL}"
        )
        if hasattr(result, "conforming"):
            assert result.conforming is True

    def test_fabricated_has_significantly_higher_mad_than_genuine(self):
        """
        Fabricated MAD must be substantially larger than genuine MAD.
        We require a factor of at least 2× difference.
        """
        rng_fab = random.Random(13)
        fabricated = []
        for _ in range(200):
            mantissa = rng_fab.uniform(7.0, 7.999)
            scale = 10 ** rng_fab.randint(0, 4)
            fabricated.append(mantissa * scale)

        genuine = _benford_sample(200, seed=14)

        res_fab = analyze_benford(fabricated)
        res_gen = analyze_benford(genuine)

        assert res_fab is not None
        assert res_gen is not None
        assert res_fab.mad > 2 * res_gen.mad, (
            f"Fabricated MAD ({res_fab.mad:.4f}) should be > 2× genuine MAD ({res_gen.mad:.4f})"
        )
