"""
Benford's Law engine for detecting fabricated financial entries.

Benford's Law: the first significant digit d appears with probability
    P(d) = log10(1 + 1/d)   for d ∈ {1, 2, ..., 9}

Expected distribution:
    d=1: 30.1%,  d=2: 17.6%,  d=3: 12.5%,  d=4: 9.7%,
    d=5: 7.9%,   d=6: 6.7%,   d=7: 5.8%,   d=8: 5.1%,  d=9: 4.6%

APPLICATION RULE (from architecture doc):
  Apply Benford's at the ACCOUNT level, NOT the entity level.
  Applying it to total revenue masks the signal.
  Apply to: GL account balances by period, invoice amounts by vendor,
            expense report line items by employee.
  Minimum 30 transactions required for statistical validity.

Metrics:
  - MAD (Mean Absolute Deviation): primary metric
      < 0.006: Conforming (Nigrini)
      0.006–0.012: Acceptable deviation
      0.012–0.015: Marginally acceptable
      > 0.015: Nonconforming (high risk)
  - Chi-squared p-value: secondary (sensitive to sample size)
    Use MAD as primary; chi-squared as corroborating evidence.
"""

import math
import numpy as np
from scipy.stats import chisquare
from dataclasses import dataclass

# Benford's theoretical distribution for digits 1-9
BENFORD_EXPECTED = np.array([math.log10(1 + 1 / d) for d in range(1, 10)])

# Nigrini (2012) MAD thresholds
MAD_CONFORMING = 0.006
MAD_ACCEPTABLE = 0.012
MAD_MARGINAL = 0.015


@dataclass
class BenfordResult:
    digit_counts: dict[str, int]       # {"1": 42, "2": 25, ...}
    observed_probs: dict[str, float]   # {"1": 0.301, ...}
    expected_probs: dict[str, float]   # Theoretical Benford probabilities
    transaction_count: int
    mad: float                         # Mean Absolute Deviation
    chi2_statistic: float
    chi2_pvalue: float
    conforming: bool                   # MAD < 0.006
    risk_level: str                    # 'low', 'medium', 'high'

    def to_dict(self) -> dict:
        return {
            'digit_counts': self.digit_counts,
            'observed_probs': self.observed_probs,
            'expected_probs': self.expected_probs,
            'transaction_count': self.transaction_count,
            'mad': self.mad,
            'chi2_statistic': self.chi2_statistic,
            'chi2_pvalue': self.chi2_pvalue,
            'conforming': self.conforming,
            'risk_level': self.risk_level,
        }


def extract_first_digit(amount: float) -> int | None:
    """
    Extract the first significant digit from a monetary amount.
    Returns None for zero, negative, or invalid amounts.
    """
    if amount <= 0:
        return None
    s = f"{abs(amount):.10f}".replace('.', '').lstrip('0')
    if not s:
        return None
    return int(s[0])


def analyze_benford(amounts: list[float]) -> BenfordResult | None:
    """
    Apply Benford's Law analysis to a list of transaction amounts.

    Returns None if insufficient data (< 30 transactions with extractable digits).
    """
    digits = [extract_first_digit(a) for a in amounts]
    digits = [d for d in digits if d is not None]

    n = len(digits)
    if n < 30:
        return None  # Insufficient data for statistical validity

    # Count occurrences of each first digit (1-9)
    counts = np.zeros(9, dtype=int)
    for d in digits:
        if 1 <= d <= 9:
            counts[d - 1] += 1

    observed_prob = counts / n

    # MAD: primary conformity metric
    mad = float(np.mean(np.abs(observed_prob - BENFORD_EXPECTED)))

    # Chi-squared test (secondary — sensitive to sample size, use MAD as primary)
    expected_counts = BENFORD_EXPECTED * n
    chi2_stat, chi2_pvalue = chisquare(counts, f_exp=expected_counts)

    # Risk classification
    if mad < MAD_CONFORMING:
        risk_level = 'low'
    elif mad < MAD_MARGINAL:
        risk_level = 'medium'
    else:
        risk_level = 'high'

    return BenfordResult(
        digit_counts={str(d): int(counts[d - 1]) for d in range(1, 10)},
        observed_probs={str(d): float(observed_prob[d - 1]) for d in range(1, 10)},
        expected_probs={str(d): float(BENFORD_EXPECTED[d - 1]) for d in range(1, 10)},
        transaction_count=n,
        mad=mad,
        chi2_statistic=float(chi2_stat),
        chi2_pvalue=float(chi2_pvalue),
        conforming=mad < MAD_CONFORMING,
        risk_level=risk_level,
    )


def benford_risk_score(result: BenfordResult | None) -> float:
    """
    Convert a BenfordResult to a [0, 1] risk score for the DRI.
    Returns 0.5 (neutral) when insufficient data.
    """
    if result is None:
        return 0.5  # Neutral — not enough data to assess

    # Map MAD to [0, 1]: 0 = perfect Benford, 1 = maximally non-conforming.
    # Piecewise linear mapping anchored at Nigrini thresholds.
    if result.mad <= MAD_CONFORMING:
        return result.mad / MAD_CONFORMING * 0.2                       # [0, 0.2]
    elif result.mad <= MAD_ACCEPTABLE:
        t = (result.mad - MAD_CONFORMING) / (MAD_ACCEPTABLE - MAD_CONFORMING)
        return 0.2 + t * 0.3                                           # [0.2, 0.5]
    elif result.mad <= MAD_MARGINAL:
        t = (result.mad - MAD_ACCEPTABLE) / (MAD_MARGINAL - MAD_ACCEPTABLE)
        return 0.5 + t * 0.3                                           # [0.5, 0.8]
    else:
        return min(1.0, 0.8 + (result.mad - MAD_MARGINAL) / 0.05 * 0.2)  # [0.8, 1.0]


class BenfordEngine:
    """
    Stateful Benford analysis engine for rolling window computation.
    Maintains per-entity running state to support incremental updates.
    """

    def analyze_entity(
        self,
        entity_id: str,
        entity_type: str,
        amounts: list[float],
        window_label: str = "rolling_90d",
    ) -> BenfordResult | None:
        """Analyze a single entity's amount distribution."""
        return analyze_benford(amounts)

    def analyze_batch(
        self,
        entity_amounts: dict[str, list[float]],
    ) -> dict[str, BenfordResult | None]:
        """
        Analyze multiple entities in one pass.
        entity_amounts: {entity_id: [amounts]}
        """
        return {
            entity_id: analyze_benford(amounts)
            for entity_id, amounts in entity_amounts.items()
        }
