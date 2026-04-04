"""Sprint 12 — ComplianceScorer unit tests (pure computation)."""
import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "../../services/people-service"),
)

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.compliance_scorer import ComplianceScorer


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

TENANT = "00000000-0000-0000-0000-000000000004"
EMPLOYEE_ID = "E001"

_EMPLOYEE = {
    "employee_id": EMPLOYEE_ID,
    "full_name": "Alice Smith",
    "department": "Engineering",
    "job_role": "engineer",
}


@pytest.fixture
def scorer():
    return ComplianceScorer()


def _make_pool():
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


def _patch_scorer(scorer, *, policy_statuses, training_statuses, bg_status):
    """
    Patch all three manager methods directly on the scorer instance so tests
    remain isolated from DB and focus purely on the scoring computation.
    """
    scorer._policy_mgr.get_employee_ack_status = AsyncMock(return_value=policy_statuses)
    scorer._training_mgr.get_employee_training_status = AsyncMock(return_value=training_statuses)
    scorer._bgcheck_mgr.get_compliance_status = AsyncMock(return_value=bg_status)


def _policy_ack(acknowledged=True, is_overdue=False, required=True):
    return {
        "policy_id": "p1",
        "title": "Security Policy",
        "required": required,
        "acknowledged": acknowledged,
        "acknowledged_at": "2024-01-01T00:00:00Z" if acknowledged else None,
        "is_overdue": is_overdue,
        "days_until_due": 300 if (acknowledged and not is_overdue) else None,
    }


def _training_status(status="completed", is_overdue=False):
    return {
        "assignment_id": "a1",
        "course_title": "Security Awareness",
        "status": status,
        "due_date": "2024-12-31",
        "is_overdue": is_overdue,
    }


def _bg_passed():
    return {"has_valid_check": True, "latest_check": {}, "score_contribution": 1.0}


def _bg_failed():
    return {"has_valid_check": False, "latest_check": None, "score_contribution": 0.0}


def _bg_expired():
    return {"has_valid_check": False, "latest_check": {}, "score_contribution": 0.5}


# ---------------------------------------------------------------------------
# TestComplianceScorer
# ---------------------------------------------------------------------------


class TestComplianceScorer:

    @pytest.mark.asyncio
    async def test_score_100_when_all_compliant(self, scorer):
        """All policies acked, all training complete, background check passed → 100.0."""
        _patch_scorer(
            scorer,
            policy_statuses=[_policy_ack(acknowledged=True, is_overdue=False)],
            training_statuses=[_training_status(status="completed", is_overdue=False)],
            bg_status=_bg_passed(),
        )
        pool = _make_pool()
        result = await scorer.score_employee(pool, TENANT, _EMPLOYEE)

        assert result.overall_score == 100.0

    @pytest.mark.asyncio
    async def test_score_0_when_nothing_done(self, scorer):
        """No acks, no training completed, no background check → overall ≈ 0."""
        _patch_scorer(
            scorer,
            policy_statuses=[_policy_ack(acknowledged=False, is_overdue=True)],
            training_statuses=[_training_status(status="assigned", is_overdue=True)],
            bg_status=_bg_failed(),
        )
        pool = _make_pool()
        result = await scorer.score_employee(pool, TENANT, _EMPLOYEE)

        assert result.overall_score == 0.0

    @pytest.mark.asyncio
    async def test_policy_weight_is_40pct(self, scorer):
        """Policy=100%, training=0%, bgcheck=0% → overall_score ≈ 40.0."""
        _patch_scorer(
            scorer,
            policy_statuses=[_policy_ack(acknowledged=True, is_overdue=False)],
            training_statuses=[_training_status(status="assigned", is_overdue=True)],
            bg_status=_bg_failed(),
        )
        pool = _make_pool()
        result = await scorer.score_employee(pool, TENANT, _EMPLOYEE)

        # policy_score=100 * 0.4 = 40; training=0 * 0.4 = 0; bg=0 * 0.2 = 0
        assert result.overall_score == pytest.approx(40.0, abs=0.5)
        assert result.policy_score == pytest.approx(100.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_training_weight_is_40pct(self, scorer):
        """Training=100%, policy=0%, bgcheck=0% → overall_score ≈ 40.0."""
        _patch_scorer(
            scorer,
            policy_statuses=[_policy_ack(acknowledged=False, is_overdue=True)],
            training_statuses=[_training_status(status="completed", is_overdue=False)],
            bg_status=_bg_failed(),
        )
        pool = _make_pool()
        result = await scorer.score_employee(pool, TENANT, _EMPLOYEE)

        # training_score=100 * 0.4 = 40; policy=0 * 0.4 = 0; bg=0 * 0.2 = 0
        assert result.overall_score == pytest.approx(40.0, abs=0.5)
        assert result.training_score == pytest.approx(100.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_bgcheck_weight_is_20pct(self, scorer):
        """Bgcheck=100%, policy=0%, training=0% → overall_score ≈ 20.0."""
        _patch_scorer(
            scorer,
            policy_statuses=[_policy_ack(acknowledged=False, is_overdue=True)],
            training_statuses=[_training_status(status="assigned", is_overdue=True)],
            bg_status=_bg_passed(),
        )
        pool = _make_pool()
        result = await scorer.score_employee(pool, TENANT, _EMPLOYEE)

        # bg_score=100 * 0.2 = 20; policy=0 * 0.4 = 0; training=0 * 0.4 = 0
        assert result.overall_score == pytest.approx(20.0, abs=0.5)
        assert result.background_check_score == pytest.approx(100.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_status_compliant_at_90(self, scorer):
        """overall_score=90.0 → status='compliant'."""
        # Achieve ≈90: policy=100*(0.4)=40, training=100*(0.4)=40, bg=50*(0.2)=10 → 90
        _patch_scorer(
            scorer,
            policy_statuses=[_policy_ack(acknowledged=True, is_overdue=False)],
            training_statuses=[_training_status(status="completed", is_overdue=False)],
            bg_status=_bg_expired(),  # score_contribution=0.5 → bg_score=50 → 50*0.2=10
        )
        pool = _make_pool()
        result = await scorer.score_employee(pool, TENANT, _EMPLOYEE)

        assert result.overall_score == pytest.approx(90.0, abs=0.5)
        assert result.status == "compliant"

    @pytest.mark.asyncio
    async def test_status_at_risk_at_75(self, scorer):
        """A score between 70 and 89 → status='at_risk'."""
        # policy=100*(0.4)=40, training=75*(0.4)=30, bg=100*(0.2)=20 → 90 is too high.
        # Use policy=75*(0.4)=30, training=75*(0.4)=30, bg=100*(0.2)=20 → 80, but
        # easiest: 3 policies, 2 acked; training all done; bg failed
        # policy=2/3*100≈66.7*0.4=26.7, training=100*0.4=40, bg=100*0.2=20 → 86.7
        # Simpler: patch _status_from_score by feeding a known score.
        # Use: 2/4 policies acked → 50*0.4=20, training=100*0.4=40, bg=100*0.2=20 → 80 → at_risk
        _patch_scorer(
            scorer,
            policy_statuses=[
                _policy_ack(acknowledged=True, is_overdue=False),
                _policy_ack(acknowledged=True, is_overdue=False),
                _policy_ack(acknowledged=False, is_overdue=True),
                _policy_ack(acknowledged=False, is_overdue=True),
            ],
            training_statuses=[_training_status(status="completed", is_overdue=False)],
            bg_status=_bg_passed(),
        )
        pool = _make_pool()
        result = await scorer.score_employee(pool, TENANT, _EMPLOYEE)

        # policy_score = 2/4 * 100 = 50; 50*0.4=20; training=100*0.4=40; bg=100*0.2=20 → 80
        assert result.overall_score == pytest.approx(80.0, abs=1.0)
        assert result.status == "at_risk"

    @pytest.mark.asyncio
    async def test_status_non_compliant_below_70(self, scorer):
        """overall_score < 70 → status='non_compliant'."""
        # 1/4 acked → policy=25*0.4=10, training=100*0.4=40, bg=0 → 50
        _patch_scorer(
            scorer,
            policy_statuses=[
                _policy_ack(acknowledged=True, is_overdue=False),
                _policy_ack(acknowledged=False, is_overdue=True),
                _policy_ack(acknowledged=False, is_overdue=True),
                _policy_ack(acknowledged=False, is_overdue=True),
            ],
            training_statuses=[_training_status(status="completed", is_overdue=False)],
            bg_status=_bg_failed(),
        )
        pool = _make_pool()
        result = await scorer.score_employee(pool, TENANT, _EMPLOYEE)

        # policy=25*0.4=10, training=100*0.4=40, bg=0*0.2=0 → 50
        assert result.overall_score < 70.0
        assert result.status == "non_compliant"

    @pytest.mark.asyncio
    async def test_expired_bgcheck_scores_half(self, scorer):
        """Expired background check: score_contribution=0.5 → contributes 0.5*0.2=10 pts."""
        _patch_scorer(
            scorer,
            policy_statuses=[],    # no policies → policy_score=100 (none required)
            training_statuses=[],  # no assignments → training_score=100
            bg_status=_bg_expired(),  # score_contribution=0.5
        )
        pool = _make_pool()
        result = await scorer.score_employee(pool, TENANT, _EMPLOYEE)

        # policy=100*0.4=40, training=100*0.4=40, bg=50*0.2=10 → 90
        assert result.background_check_score == pytest.approx(50.0, abs=0.5)
        assert result.overall_score == pytest.approx(90.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_partial_policy_compliance(self, scorer):
        """3 of 4 policies acked → policy_score=75.0 → contributes 30.0 to overall."""
        _patch_scorer(
            scorer,
            policy_statuses=[
                _policy_ack(acknowledged=True, is_overdue=False),
                _policy_ack(acknowledged=True, is_overdue=False),
                _policy_ack(acknowledged=True, is_overdue=False),
                _policy_ack(acknowledged=False, is_overdue=True),
            ],
            training_statuses=[],  # no assignments → training_score=100
            bg_status=_bg_failed(),
        )
        pool = _make_pool()
        result = await scorer.score_employee(pool, TENANT, _EMPLOYEE)

        # policy_score = 3/4 * 100 = 75
        assert result.policy_score == pytest.approx(75.0, abs=0.1)
        # policy contribution = 75 * 0.4 = 30
        # training = 100 * 0.4 = 40; bg = 0 * 0.2 = 0 → overall = 70
        assert result.overall_score == pytest.approx(70.0, abs=0.5)
