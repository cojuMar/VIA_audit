"""
Pure computation module — no DB access.
Provides score, label, color, and risk_reduction helpers.
"""

SCORE_LABELS: dict[tuple[int, int], str] = {
    (1, 1): "Very Low",
    (1, 2): "Low",
    (1, 3): "Low",
    (1, 4): "Medium",
    (1, 5): "Medium",
    (2, 1): "Low",
    (2, 2): "Low",
    (2, 3): "Medium",
    (2, 4): "Medium",
    (2, 5): "High",
    (3, 1): "Low",
    (3, 2): "Medium",
    (3, 3): "Medium",
    (3, 4): "High",
    (3, 5): "High",
    (4, 1): "Medium",
    (4, 2): "Medium",
    (4, 3): "High",
    (4, 4): "High",
    (4, 5): "Critical",
    (5, 1): "Medium",
    (5, 2): "High",
    (5, 3): "High",
    (5, 4): "Critical",
    (5, 5): "Critical",
}


class RiskScorer:
    def score(self, likelihood: int, impact: int) -> float:
        return float(likelihood * impact)

    def label(self, likelihood: int, impact: int) -> str:
        return SCORE_LABELS.get((likelihood, impact), "Unknown")

    def color(self, likelihood: int, impact: int) -> str:
        s = likelihood * impact
        if s >= 20:
            return "red"
        if s >= 12:
            return "orange"
        if s >= 6:
            return "yellow"
        return "green"

    def risk_reduction(
        self,
        inherent_l: int,
        inherent_i: int,
        residual_l: int,
        residual_i: int,
    ) -> float:
        """Returns % reduction in score from inherent to residual."""
        inherent = inherent_l * inherent_i
        residual = residual_l * residual_i
        if inherent == 0:
            return 0.0
        return round((1 - residual / inherent) * 100, 1)


# ---------------------------------------------------------------------------
# Module-level convenience functions (delegate to a shared instance)
# ---------------------------------------------------------------------------

_scorer = RiskScorer()


def score(likelihood: int, impact: int) -> float:
    """Return likelihood × impact as a float."""
    return _scorer.score(likelihood, impact)


def label(likelihood: int, impact: int) -> str:
    """Return the human-readable risk label for the given cell."""
    return _scorer.label(likelihood, impact)


def color(likelihood: int, impact: int) -> str:
    """Return the heat-map colour string for the given cell."""
    return _scorer.color(likelihood, impact)


def risk_reduction(
    inherent_l: int,
    inherent_i: int,
    residual_l: int,
    residual_i: int,
) -> float:
    """Return the percentage score reduction from inherent to residual."""
    return _scorer.risk_reduction(inherent_l, inherent_i, residual_l, residual_i)
