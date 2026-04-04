from __future__ import annotations

import asyncpg

from .db import tenant_conn
from .models import EmployeeCreate


class EmployeeManager:

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _record_to_dict(record: asyncpg.Record) -> dict:
        return dict(record)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create(
        self, pool: asyncpg.Pool, tenant_id: str, data: EmployeeCreate
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO employees (
                    tenant_id, employee_id, full_name, email,
                    department, job_title, job_role, manager_id, hire_date
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (tenant_id, employee_id) DO UPDATE SET
                    full_name   = EXCLUDED.full_name,
                    email       = EXCLUDED.email,
                    department  = EXCLUDED.department,
                    job_title   = EXCLUDED.job_title,
                    job_role    = EXCLUDED.job_role,
                    manager_id  = EXCLUDED.manager_id,
                    hire_date   = EXCLUDED.hire_date,
                    updated_at  = NOW()
                RETURNING *
                """,
                tenant_id,
                data.employee_id,
                data.full_name,
                data.email,
                data.department,
                data.job_title,
                data.job_role,
                data.manager_id,
                data.hire_date,
            )
            return self._record_to_dict(row)

    async def bulk_upsert(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        employees: list[EmployeeCreate],
    ) -> dict:
        created = 0
        updated = 0

        async with tenant_conn(pool, tenant_id) as conn:
            for emp in employees:
                # Check if the employee already exists to distinguish create vs update
                existing = await conn.fetchrow(
                    "SELECT id FROM employees WHERE tenant_id=$1 AND employee_id=$2",
                    tenant_id,
                    emp.employee_id,
                )
                await conn.execute(
                    """
                    INSERT INTO employees (
                        tenant_id, employee_id, full_name, email,
                        department, job_title, job_role, manager_id, hire_date
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (tenant_id, employee_id) DO UPDATE SET
                        full_name   = EXCLUDED.full_name,
                        email       = EXCLUDED.email,
                        department  = EXCLUDED.department,
                        job_title   = EXCLUDED.job_title,
                        job_role    = EXCLUDED.job_role,
                        manager_id  = EXCLUDED.manager_id,
                        hire_date   = EXCLUDED.hire_date,
                        updated_at  = NOW()
                    """,
                    tenant_id,
                    emp.employee_id,
                    emp.full_name,
                    emp.email,
                    emp.department,
                    emp.job_title,
                    emp.job_role,
                    emp.manager_id,
                    emp.hire_date,
                )
                if existing:
                    updated += 1
                else:
                    created += 1

        return {"created": created, "updated": updated}

    async def get(
        self, pool: asyncpg.Pool, tenant_id: str, employee_id: str
    ) -> dict | None:
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                "SELECT * FROM employees WHERE tenant_id=$1 AND employee_id=$2",
                tenant_id,
                employee_id,
            )
            return self._record_to_dict(row) if row else None

    async def list_active(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        department: str | None = None,
        job_role: str | None = None,
    ) -> list[dict]:
        conditions = ["tenant_id=$1", "employment_status='active'"]
        params: list = [tenant_id]
        idx = 2

        if department:
            conditions.append(f"department=${idx}")
            params.append(department)
            idx += 1
        if job_role:
            conditions.append(f"job_role=${idx}")
            params.append(job_role)
            idx += 1

        query = f"SELECT * FROM employees WHERE {' AND '.join(conditions)} ORDER BY full_name"
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(query, *params)
            return [self._record_to_dict(r) for r in rows]

    async def update_status(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        employee_id: str,
        status: str,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                UPDATE employees
                SET employment_status=$3, updated_at=NOW()
                WHERE tenant_id=$1 AND employee_id=$2
                RETURNING *
                """,
                tenant_id,
                employee_id,
                status,
            )
            if row is None:
                raise ValueError(f"Employee {employee_id} not found")
            return self._record_to_dict(row)

    async def get_summary(self, pool: asyncpg.Pool, tenant_id: str) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            total_row = await conn.fetchrow(
                "SELECT COUNT(*) AS total FROM employees WHERE tenant_id=$1",
                tenant_id,
            )
            status_rows = await conn.fetch(
                """
                SELECT employment_status, COUNT(*) AS cnt
                FROM employees
                WHERE tenant_id=$1
                GROUP BY employment_status
                """,
                tenant_id,
            )
            dept_rows = await conn.fetch(
                """
                SELECT department, COUNT(*) AS cnt
                FROM employees
                WHERE tenant_id=$1 AND employment_status='active' AND department IS NOT NULL
                GROUP BY department
                ORDER BY cnt DESC
                """,
                tenant_id,
            )
            role_rows = await conn.fetch(
                """
                SELECT job_role, COUNT(*) AS cnt
                FROM employees
                WHERE tenant_id=$1 AND employment_status='active'
                GROUP BY job_role
                ORDER BY cnt DESC
                """,
                tenant_id,
            )

        status_map: dict[str, int] = {r["employment_status"]: r["cnt"] for r in status_rows}

        return {
            "total": total_row["total"],
            "active": status_map.get("active", 0),
            "on_leave": status_map.get("on_leave", 0),
            "terminated": status_map.get("terminated", 0),
            "by_department": {r["department"]: r["cnt"] for r in dept_rows},
            "by_role": {r["job_role"]: r["cnt"] for r in role_rows},
        }
