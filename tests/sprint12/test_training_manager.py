"""Sprint 12 — TrainingManager unit tests."""
import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "../../services/people-service"),
)

import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, call

from src.training_manager import TrainingManager
from src.models import TrainingAssignmentCreate, TrainingCompletion, TrainingCourseCreate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT = "00000000-0000-0000-0000-000000000003"
COURSE_ID = "dddd0000-0000-0000-0000-000000000001"
ASSIGNMENT_ID = "eeee0000-0000-0000-0000-000000000001"
EMPLOYEE_ID = "E001"

_COURSE_DICT = {
    "id": COURSE_ID,
    "tenant_id": TENANT,
    "course_key": "sec-awareness-2024",
    "title": "Security Awareness Training",
    "description": None,
    "category": "security_awareness",
    "applies_to_roles": ["all"],
    "duration_minutes": 60,
    "passing_score_pct": 80,
    "recurrence_days": None,
    "provider": "internal",
    "is_active": True,
}

_ASSIGNMENT_DICT = {
    "id": ASSIGNMENT_ID,
    "tenant_id": TENANT,
    "course_id": COURSE_ID,
    "employee_id": EMPLOYEE_ID,
    "status": "assigned",
    "due_date": date.today() + timedelta(days=30),
    "assigned_at": date.today(),
    "reminder_sent_count": 0,
}

_COMPLETION_DICT = {
    "id": "ffff0000-0000-0000-0000-000000000001",
    "tenant_id": TENANT,
    "assignment_id": ASSIGNMENT_ID,
    "employee_id": EMPLOYEE_ID,
    "course_id": COURSE_ID,
    "completed_at": date.today(),
    "score_pct": 90,
    "passed": True,
    "completion_method": "portal",
}


def make_pool_with_conn(conn):
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


def make_transactional_conn():
    conn = AsyncMock()
    tx = AsyncMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    return conn


def make_course(**kwargs):
    defaults = dict(
        course_key="sec-awareness-2024",
        title="Security Awareness Training",
        description=None,
        category="security_awareness",
        applies_to_roles=["all"],
        duration_minutes=60,
        passing_score_pct=80,
        recurrence_days=None,
        provider="internal",
    )
    defaults.update(kwargs)
    return TrainingCourseCreate(**defaults)


def make_assignment(**kwargs):
    defaults = dict(
        course_id=COURSE_ID,
        employee_id=EMPLOYEE_ID,
        due_date=date.today() + timedelta(days=30),
    )
    defaults.update(kwargs)
    return TrainingAssignmentCreate(**defaults)


def make_completion(**kwargs):
    defaults = dict(
        assignment_id=ASSIGNMENT_ID,
        employee_id=EMPLOYEE_ID,
        course_id=COURSE_ID,
        score_pct=90,
        passed=True,
        completion_method="portal",
        external_completion_id=None,
    )
    defaults.update(kwargs)
    return TrainingCompletion(**defaults)


# ---------------------------------------------------------------------------
# TestTrainingManager
# ---------------------------------------------------------------------------


class TestTrainingManager:

    @pytest.mark.asyncio
    async def test_create_course_inserts_row(self):
        """create_course() calls fetchrow with an INSERT INTO training_courses."""
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=_COURSE_DICT)
        pool = make_pool_with_conn(conn)

        mgr = TrainingManager()
        result = await mgr.create_course(pool, TENANT, make_course())

        conn.fetchrow.assert_called_once()
        query = conn.fetchrow.call_args[0][0]
        assert "INSERT INTO training_courses" in query
        assert result["title"] == "Security Awareness Training"

    @pytest.mark.asyncio
    async def test_assign_course_inserts_assignment(self):
        """assign_course() inserts a new assignment when no duplicate exists."""
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[None, _ASSIGNMENT_DICT])
        pool = make_pool_with_conn(conn)

        mgr = TrainingManager()
        result = await mgr.assign_course(pool, TENANT, make_assignment())

        # Second fetchrow should be the INSERT RETURNING
        assert conn.fetchrow.call_count == 2
        insert_query = conn.fetchrow.call_args_list[1][0][0]
        assert "INSERT INTO training_assignments" in insert_query

    @pytest.mark.asyncio
    async def test_assign_course_skips_duplicate(self):
        """assign_course() raises ValueError when an active assignment already exists.

        The implementation prevents duplicate active assignments.  The test
        confirms that no INSERT is attempted when the duplicate-check fetchrow
        returns an existing row, and that the caller is informed via ValueError.
        """
        conn = AsyncMock()
        # First fetchrow (duplicate check) returns an existing row
        existing = {"id": ASSIGNMENT_ID}
        conn.fetchrow = AsyncMock(return_value=existing)
        pool = make_pool_with_conn(conn)

        mgr = TrainingManager()

        with pytest.raises(ValueError):
            await mgr.assign_course(pool, TENANT, make_assignment())

        # Only one fetchrow call (the duplicate check); no INSERT fetchrow
        assert conn.fetchrow.call_count == 1

    @pytest.mark.asyncio
    async def test_bulk_assign_returns_counts(self):
        """bulk_assign with 5 employees, 1 already assigned → {assigned:4, skipped_duplicates:1}."""
        conn = AsyncMock()
        existing = {"id": ASSIGNMENT_ID}
        # 5 employees: first is existing, rest are new
        conn.fetchrow = AsyncMock(
            side_effect=[existing, None, None, None, None]
        )
        conn.execute = AsyncMock(return_value=None)
        pool = make_pool_with_conn(conn)

        employee_ids = [f"E00{i}" for i in range(1, 6)]
        mgr = TrainingManager()
        result = await mgr.bulk_assign(pool, TENANT, COURSE_ID, employee_ids, None)

        assert result["assigned"] == 4
        assert result["skipped_duplicates"] == 1

    @pytest.mark.asyncio
    async def test_record_completion_inserts_immutable_record(self):
        """record_completion() inserts into training_completions (immutable table)."""
        conn = make_transactional_conn()
        course_without_recurrence = dict(_COURSE_DICT, recurrence_days=None)
        conn.fetchrow = AsyncMock(
            side_effect=[_COMPLETION_DICT, course_without_recurrence]
        )
        conn.execute = AsyncMock(return_value=None)
        pool = make_pool_with_conn(conn)

        mgr = TrainingManager()
        await mgr.record_completion(pool, TENANT, make_completion())

        # First fetchrow is the INSERT INTO training_completions
        insert_query = conn.fetchrow.call_args_list[0][0][0]
        assert "INSERT INTO training_completions" in insert_query

    @pytest.mark.asyncio
    async def test_record_completion_updates_assignment_status(self):
        """record_completion() updates training_assignments status to 'completed'."""
        conn = make_transactional_conn()
        course_without_recurrence = dict(_COURSE_DICT, recurrence_days=None)
        conn.fetchrow = AsyncMock(
            side_effect=[_COMPLETION_DICT, course_without_recurrence]
        )
        conn.execute = AsyncMock(return_value=None)
        pool = make_pool_with_conn(conn)

        mgr = TrainingManager()
        await mgr.record_completion(pool, TENANT, make_completion(passed=True))

        execute_queries = [c[0][0] for c in conn.execute.call_args_list]
        update_queries = [q for q in execute_queries if "UPDATE training_assignments" in q]
        assert len(update_queries) == 1

        # Verify 'completed' is passed as a parameter in the UPDATE call
        update_call = [
            c for c in conn.execute.call_args_list
            if "UPDATE training_assignments" in c[0][0]
        ][0]
        assert "completed" in update_call[0]

    @pytest.mark.asyncio
    async def test_record_failed_completion_sets_failed_status(self):
        """passed=False → assignment status set to 'failed'."""
        conn = make_transactional_conn()
        failed_completion = dict(_COMPLETION_DICT, passed=False)
        conn.fetchrow = AsyncMock(return_value=failed_completion)
        conn.execute = AsyncMock(return_value=None)
        pool = make_pool_with_conn(conn)

        mgr = TrainingManager()
        await mgr.record_completion(pool, TENANT, make_completion(passed=False))

        update_call = [
            c for c in conn.execute.call_args_list
            if "UPDATE training_assignments" in c[0][0]
        ][0]
        assert "failed" in update_call[0]

    @pytest.mark.asyncio
    async def test_record_completion_with_recurrence_creates_next_assignment(self):
        """Course with recurrence_days=365 → new assignment INSERT after completion."""
        conn = make_transactional_conn()
        course_with_recurrence = dict(_COURSE_DICT, recurrence_days=365)
        conn.fetchrow = AsyncMock(
            side_effect=[_COMPLETION_DICT, course_with_recurrence, None]
        )
        conn.execute = AsyncMock(return_value=None)
        pool = make_pool_with_conn(conn)

        mgr = TrainingManager()
        await mgr.record_completion(pool, TENANT, make_completion(passed=True))

        execute_queries = [c[0][0] for c in conn.execute.call_args_list]
        recurrence_inserts = [
            q for q in execute_queries
            if "INSERT INTO training_assignments" in q
        ]
        assert len(recurrence_inserts) >= 1

    @pytest.mark.asyncio
    async def test_get_employee_training_status_returns_list(self):
        """get_employee_training_status() returns a list of assignment dicts."""
        conn = AsyncMock()
        status_rows = [
            dict(_ASSIGNMENT_DICT, course_title="Security Awareness"),
            dict(_ASSIGNMENT_DICT, id="assign-002", course_title="Privacy Training"),
        ]
        conn.fetch = AsyncMock(return_value=status_rows)
        pool = make_pool_with_conn(conn)

        mgr = TrainingManager()
        result = await mgr.get_employee_training_status(pool, TENANT, EMPLOYEE_ID)

        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_overdue_assignments_filtered_by_date(self):
        """Assignment with due_date yesterday + status='assigned' → appears in overdue list."""
        conn = AsyncMock()
        yesterday = date.today() - timedelta(days=1)
        overdue_assignment = dict(
            _ASSIGNMENT_DICT,
            due_date=yesterday,
            status="assigned",
            course_title="Security Awareness",
        )
        conn.fetch = AsyncMock(return_value=[overdue_assignment])
        pool = make_pool_with_conn(conn)

        mgr = TrainingManager()
        result = await mgr.get_overdue_assignments(pool, TENANT)

        assert len(result) == 1
        assert result[0]["status"] == "assigned"

        # Verify the query filters by date and status
        query = conn.fetch.call_args[0][0]
        assert "due_date" in query.lower()

    @pytest.mark.asyncio
    async def test_update_overdue_statuses_returns_count(self):
        """update_overdue_statuses() returns count of rows updated."""
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="UPDATE 3")
        pool = make_pool_with_conn(conn)

        mgr = TrainingManager()
        count = await mgr.update_overdue_statuses(pool, TENANT)

        assert count == 3
        conn.execute.assert_called_once()
        query = conn.execute.call_args[0][0]
        assert "UPDATE training_assignments" in query

    @pytest.mark.asyncio
    async def test_get_training_compliance_rate_structure(self):
        """get_training_compliance_rate() returns dict with required top-level keys."""
        conn = AsyncMock()
        totals_row = {"total": 20, "completed": 14}
        rate_30d_row = {"completed_30d": 8}
        course_rows = [
            {"course_id": COURSE_ID, "title": "Sec Awareness", "total": 10, "completed": 8},
        ]
        dept_rows = [
            {"department": "Engineering", "total": 10, "completed": 7},
        ]
        conn.fetchrow = AsyncMock(side_effect=[totals_row, rate_30d_row])
        conn.fetch = AsyncMock(side_effect=[course_rows, dept_rows])
        pool = make_pool_with_conn(conn)

        mgr = TrainingManager()
        result = await mgr.get_training_compliance_rate(pool, TENANT)

        assert "overall_pct" in result
        assert "completion_rate_30d" in result
        assert "by_course" in result
        assert "by_department" in result
