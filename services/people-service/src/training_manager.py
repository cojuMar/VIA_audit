from __future__ import annotations

from datetime import date, timedelta

import asyncpg

from .db import tenant_conn
from .models import TrainingAssignmentCreate, TrainingCompletion, TrainingCourseCreate


class TrainingManager:

    @staticmethod
    def _to_dict(record: asyncpg.Record) -> dict:
        return dict(record)

    # ------------------------------------------------------------------

    async def create_course(
        self, pool: asyncpg.Pool, tenant_id: str, data: TrainingCourseCreate
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO training_courses (
                    tenant_id, course_key, title, description, category,
                    applies_to_roles, duration_minutes, passing_score_pct,
                    recurrence_days, provider
                )
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                RETURNING *
                """,
                tenant_id,
                data.course_key,
                data.title,
                data.description,
                data.category,
                data.applies_to_roles,
                data.duration_minutes,
                data.passing_score_pct,
                data.recurrence_days,
                data.provider,
            )
            return self._to_dict(row)

    async def list_courses(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        category: str | None = None,
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            if category:
                rows = await conn.fetch(
                    "SELECT * FROM training_courses WHERE tenant_id=$1 AND category=$2 "
                    "AND is_active=TRUE ORDER BY title",
                    tenant_id,
                    category,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM training_courses WHERE tenant_id=$1 AND is_active=TRUE ORDER BY title",
                    tenant_id,
                )
            return [self._to_dict(r) for r in rows]

    async def assign_course(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        data: TrainingAssignmentCreate,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            # Check for an existing active assignment to avoid duplicates
            existing = await conn.fetchrow(
                """
                SELECT id FROM training_assignments
                WHERE tenant_id=$1 AND course_id=$2 AND employee_id=$3
                  AND status IN ('assigned','in_progress')
                """,
                tenant_id,
                data.course_id,
                data.employee_id,
            )
            if existing:
                raise ValueError(
                    f"Active assignment already exists for employee {data.employee_id} "
                    f"on course {data.course_id}"
                )
            row = await conn.fetchrow(
                """
                INSERT INTO training_assignments (
                    tenant_id, course_id, employee_id, due_date, status
                )
                VALUES ($1,$2,$3,$4,'assigned')
                RETURNING *
                """,
                tenant_id,
                data.course_id,
                data.employee_id,
                data.due_date,
            )
            return self._to_dict(row)

    async def bulk_assign(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        course_id: str,
        employee_ids: list[str],
        due_date: date | None,
    ) -> dict:
        assigned = 0
        skipped_duplicates = 0

        async with tenant_conn(pool, tenant_id) as conn:
            for emp_id in employee_ids:
                existing = await conn.fetchrow(
                    """
                    SELECT id FROM training_assignments
                    WHERE tenant_id=$1 AND course_id=$2 AND employee_id=$3
                      AND status IN ('assigned','in_progress')
                    """,
                    tenant_id,
                    course_id,
                    emp_id,
                )
                if existing:
                    skipped_duplicates += 1
                    continue
                await conn.execute(
                    """
                    INSERT INTO training_assignments (
                        tenant_id, course_id, employee_id, due_date, status
                    )
                    VALUES ($1,$2,$3,$4,'assigned')
                    """,
                    tenant_id,
                    course_id,
                    emp_id,
                    due_date,
                )
                assigned += 1

        return {"assigned": assigned, "skipped_duplicates": skipped_duplicates}

    async def record_completion(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        data: TrainingCompletion,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            async with conn.transaction():
                # 1. INSERT completion (immutable)
                completion_row = await conn.fetchrow(
                    """
                    INSERT INTO training_completions (
                        tenant_id, assignment_id, employee_id, course_id,
                        score_pct, passed, completion_method, external_completion_id
                    )
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                    RETURNING *
                    """,
                    tenant_id,
                    data.assignment_id,
                    data.employee_id,
                    data.course_id,
                    data.score_pct,
                    data.passed,
                    data.completion_method,
                    data.external_completion_id,
                )

                # 2. UPDATE the assignment status
                new_status = "completed" if data.passed else "failed"
                await conn.execute(
                    """
                    UPDATE training_assignments
                    SET status=$3, completed_at=NOW(), updated_at=NOW()
                    WHERE tenant_id=$1 AND id=$2
                    """,
                    tenant_id,
                    data.assignment_id,
                    new_status,
                )

                # 3. Auto-assign next cycle if course has recurrence
                if data.passed:
                    course = await conn.fetchrow(
                        "SELECT recurrence_days FROM training_courses "
                        "WHERE tenant_id=$1 AND id=$2",
                        tenant_id,
                        data.course_id,
                    )
                    if course and course["recurrence_days"]:
                        next_due = date.today() + timedelta(days=course["recurrence_days"])
                        # Only create if no active assignment already exists
                        dup = await conn.fetchrow(
                            """
                            SELECT id FROM training_assignments
                            WHERE tenant_id=$1 AND course_id=$2 AND employee_id=$3
                              AND status IN ('assigned','in_progress')
                            """,
                            tenant_id,
                            data.course_id,
                            data.employee_id,
                        )
                        if not dup:
                            await conn.execute(
                                """
                                INSERT INTO training_assignments (
                                    tenant_id, course_id, employee_id, due_date, status
                                )
                                VALUES ($1,$2,$3,$4,'assigned')
                                """,
                                tenant_id,
                                data.course_id,
                                data.employee_id,
                                next_due,
                            )

                return self._to_dict(completion_row)

    async def get_employee_training_status(
        self, pool: asyncpg.Pool, tenant_id: str, employee_id: str
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT
                    ta.id           AS assignment_id,
                    tc.title        AS course_title,
                    ta.status,
                    ta.due_date,
                    ta.completed_at,
                    (
                        SELECT score_pct
                        FROM training_completions comp
                        WHERE comp.tenant_id  = ta.tenant_id
                          AND comp.assignment_id = ta.id::text
                        ORDER BY comp.created_at DESC
                        LIMIT 1
                    ) AS score_pct,
                    CASE
                        WHEN ta.status IN ('assigned','in_progress')
                             AND ta.due_date IS NOT NULL
                             AND ta.due_date < CURRENT_DATE
                        THEN TRUE ELSE FALSE
                    END AS is_overdue
                FROM training_assignments ta
                JOIN training_courses tc
                    ON tc.id = ta.course_id::uuid AND tc.tenant_id = ta.tenant_id
                WHERE ta.tenant_id  = $1
                  AND ta.employee_id = $2
                ORDER BY ta.due_date NULLS LAST
                """,
                tenant_id,
                employee_id,
            )
            return [dict(r) for r in rows]

    async def get_overdue_assignments(
        self, pool: asyncpg.Pool, tenant_id: str
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT ta.*, tc.title AS course_title, e.full_name, e.email
                FROM training_assignments ta
                JOIN training_courses tc
                    ON tc.id = ta.course_id::uuid AND tc.tenant_id = ta.tenant_id
                JOIN employees e
                    ON e.tenant_id = ta.tenant_id AND e.employee_id = ta.employee_id
                WHERE ta.tenant_id = $1
                  AND ta.status IN ('assigned','in_progress','overdue')
                  AND ta.due_date < CURRENT_DATE
                ORDER BY ta.due_date, e.full_name
                """,
                tenant_id,
            )
            return [dict(r) for r in rows]

    async def get_training_compliance_rate(
        self, pool: asyncpg.Pool, tenant_id: str
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            # Overall rate
            totals = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed
                FROM training_assignments
                WHERE tenant_id=$1
                """,
                tenant_id,
            )

            # 30-day completion rate
            rate_30d_row = await conn.fetchrow(
                """
                SELECT COUNT(*) AS completed_30d
                FROM training_completions
                WHERE tenant_id=$1 AND created_at >= NOW() - INTERVAL '30 days' AND passed=TRUE
                """,
                tenant_id,
            )

            # By course
            course_rows = await conn.fetch(
                """
                SELECT
                    tc.id     AS course_id,
                    tc.title,
                    COUNT(ta.id)                                          AS total,
                    SUM(CASE WHEN ta.status='completed' THEN 1 ELSE 0 END) AS completed
                FROM training_assignments ta
                JOIN training_courses tc ON tc.id = ta.course_id::uuid AND tc.tenant_id = ta.tenant_id
                WHERE ta.tenant_id=$1
                GROUP BY tc.id, tc.title
                ORDER BY tc.title
                """,
                tenant_id,
            )

            # By department
            dept_rows = await conn.fetch(
                """
                SELECT
                    e.department,
                    COUNT(ta.id)                                          AS total,
                    SUM(CASE WHEN ta.status='completed' THEN 1 ELSE 0 END) AS completed
                FROM training_assignments ta
                JOIN employees e ON e.tenant_id=ta.tenant_id AND e.employee_id=ta.employee_id
                WHERE ta.tenant_id=$1 AND e.department IS NOT NULL
                GROUP BY e.department
                ORDER BY e.department
                """,
                tenant_id,
            )

        total = totals["total"] or 0
        completed = totals["completed"] or 0
        overall_pct = round(completed / total * 100, 1) if total else 100.0

        def _pct(c, t):
            return round(c / t * 100, 1) if t else 0.0

        return {
            "overall_pct": overall_pct,
            "completion_rate_30d": rate_30d_row["completed_30d"],
            "by_course": [
                {
                    "course_id": str(r["course_id"]),
                    "title": r["title"],
                    "total": r["total"],
                    "completed": r["completed"],
                    "pct": _pct(r["completed"], r["total"]),
                }
                for r in course_rows
            ],
            "by_department": [
                {
                    "department": r["department"],
                    "total": r["total"],
                    "completed": r["completed"],
                    "pct": _pct(r["completed"], r["total"]),
                }
                for r in dept_rows
            ],
        }

    async def update_overdue_statuses(
        self, pool: asyncpg.Pool, tenant_id: str
    ) -> int:
        async with tenant_conn(pool, tenant_id) as conn:
            result = await conn.execute(
                """
                UPDATE training_assignments
                SET status='overdue', updated_at=NOW()
                WHERE tenant_id=$1
                  AND status IN ('assigned','in_progress')
                  AND due_date < CURRENT_DATE
                """,
                tenant_id,
            )
        # asyncpg returns "UPDATE N" as a string
        try:
            return int(result.split()[-1])
        except (IndexError, ValueError):
            return 0
