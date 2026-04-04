from __future__ import annotations

from datetime import date, timedelta

import asyncpg

from .db import tenant_conn
from .models import BackgroundCheckCreate


class BackgroundCheckManager:

    @staticmethod
    def _to_dict(record: asyncpg.Record) -> dict:
        return dict(record)

    # ------------------------------------------------------------------

    async def initiate(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        data: BackgroundCheckCreate,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO background_checks (
                    tenant_id, employee_id, check_type, provider,
                    external_check_id, expiry_date, status
                )
                VALUES ($1,$2,$3,$4,$5,$6,'pending')
                RETURNING *
                """,
                tenant_id,
                data.employee_id,
                data.check_type,
                data.provider,
                data.external_check_id,
                data.expiry_date,
            )
            return self._to_dict(row)

    async def update_status(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        check_id: str,
        status: str,
        result_summary: str | None,
        adjudication: str | None,
        completed_at: date | None,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                UPDATE background_checks
                SET status=$3,
                    result_summary=$4,
                    adjudication=$5,
                    completed_at=$6,
                    updated_at=NOW()
                WHERE tenant_id=$1 AND id=$2
                RETURNING *
                """,
                tenant_id,
                check_id,
                status,
                result_summary,
                adjudication,
                completed_at,
            )
            if row is None:
                raise ValueError(f"Background check {check_id} not found")
            return self._to_dict(row)

    async def get_employee_checks(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        employee_id: str,
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM background_checks
                WHERE tenant_id=$1 AND employee_id=$2
                ORDER BY created_at DESC
                """,
                tenant_id,
                employee_id,
            )
            return [self._to_dict(r) for r in rows]

    async def get_expired_or_expiring(
        self, pool: asyncpg.Pool, tenant_id: str, warning_days: int
    ) -> list[dict]:
        cutoff = date.today() + timedelta(days=warning_days)
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT bc.*, e.full_name, e.email
                FROM background_checks bc
                JOIN employees e ON e.tenant_id=bc.tenant_id AND e.employee_id=bc.employee_id
                WHERE bc.tenant_id=$1
                  AND bc.expiry_date IS NOT NULL
                  AND bc.expiry_date <= $2
                ORDER BY bc.expiry_date
                """,
                tenant_id,
                cutoff,
            )
            return [dict(r) for r in rows]

    async def get_summary(self, pool: asyncpg.Pool, tenant_id: str) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            total_row = await conn.fetchrow(
                "SELECT COUNT(*) AS total FROM background_checks WHERE tenant_id=$1",
                tenant_id,
            )
            status_rows = await conn.fetch(
                """
                SELECT status, COUNT(*) AS cnt
                FROM background_checks
                WHERE tenant_id=$1
                GROUP BY status
                """,
                tenant_id,
            )
            expired_row = await conn.fetchrow(
                """
                SELECT COUNT(*) AS cnt
                FROM background_checks
                WHERE tenant_id=$1 AND expiry_date < CURRENT_DATE
                """,
                tenant_id,
            )
            expiring_row = await conn.fetchrow(
                """
                SELECT COUNT(*) AS cnt
                FROM background_checks
                WHERE tenant_id=$1
                  AND expiry_date >= CURRENT_DATE
                  AND expiry_date <= CURRENT_DATE + INTERVAL '60 days'
                """,
                tenant_id,
            )

        return {
            "total": total_row["total"],
            "by_status": {r["status"]: r["cnt"] for r in status_rows},
            "expired_count": expired_row["cnt"],
            "expiring_soon_count": expiring_row["cnt"],
        }

    async def get_compliance_status(
        self, pool: asyncpg.Pool, tenant_id: str, employee_id: str
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            latest = await conn.fetchrow(
                """
                SELECT * FROM background_checks
                WHERE tenant_id=$1 AND employee_id=$2
                ORDER BY created_at DESC
                LIMIT 1
                """,
                tenant_id,
                employee_id,
            )

        if latest is None:
            return {
                "has_valid_check": False,
                "latest_check": None,
                "score_contribution": 0.0,
            }

        check = dict(latest)
        today = date.today()
        is_expired = (
            check.get("expiry_date") is not None
            and check["expiry_date"] < today
        )
        adjudication = (check.get("adjudication") or "").lower()
        status = (check.get("status") or "").lower()

        if status == "completed" and adjudication in ("clear", "passed") and not is_expired:
            score_contribution = 1.0
            has_valid = True
        elif is_expired:
            score_contribution = 0.5
            has_valid = False
        else:
            score_contribution = 0.0
            has_valid = False

        return {
            "has_valid_check": has_valid,
            "latest_check": check,
            "score_contribution": score_contribution,
        }
