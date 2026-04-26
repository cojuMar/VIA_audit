from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import Settings

logger = logging.getLogger(__name__)


class EscalationEngine:
    def __init__(self, settings: Settings) -> None:
        self.scheduler = AsyncIOScheduler()
        self.settings = settings

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, pool: asyncpg.Pool) -> None:
        if not self.settings.escalation_schedule_enabled:
            logger.info("Escalation scheduler disabled by config.")
            return

        self.scheduler.add_job(
            self._check_training_overdue,
            "cron",
            hour=8,
            minute=0,
            args=[pool],
            id="check_training_overdue",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self._check_policy_overdue,
            "cron",
            hour=8,
            minute=15,
            args=[pool],
            id="check_policy_overdue",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self._check_bgcheck_expiry,
            "cron",
            day_of_week="sun",
            hour=9,
            args=[pool],
            id="check_bgcheck_expiry",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info("EscalationEngine scheduler started.")

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("EscalationEngine scheduler stopped.")

    # ------------------------------------------------------------------
    # Platform-level tenant discovery (no RLS)
    # ------------------------------------------------------------------

    @staticmethod
    async def _get_active_tenants(pool: asyncpg.Pool) -> list[str]:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT tenant_id FROM employees WHERE employment_status='active'"
            )
            return [str(r["tenant_id"]) for r in rows]

    # ------------------------------------------------------------------
    # Deduplication helper
    # ------------------------------------------------------------------

    @staticmethod
    async def _escalation_exists(
        conn: asyncpg.Connection,
        tenant_id: str,
        employee_id: str,
        reference_id: str,
        escalation_type: str,
    ) -> bool:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)
        row = await conn.fetchrow(
            """
            SELECT id FROM compliance_escalations
            WHERE tenant_id       = $1
              AND employee_id     = $2
              AND reference_id    = $3
              AND escalation_type = $4
              AND created_at      >= $5
            LIMIT 1
            """,
            tenant_id,
            employee_id,
            reference_id,
            escalation_type,
            cutoff,
        )
        return row is not None

    @staticmethod
    async def _insert_escalation(
        conn: asyncpg.Connection,
        tenant_id: str,
        employee_id: str,
        escalation_type: str,
        reference_id: str,
        description: str,
        severity: str = "medium",
    ) -> None:
        await conn.execute(
            """
            INSERT INTO compliance_escalations (
                tenant_id, employee_id, escalation_type,
                reference_id, description, severity, status
            )
            VALUES ($1,$2,$3,$4,$5,$6,'open')
            """,
            tenant_id,
            employee_id,
            escalation_type,
            reference_id,
            description,
            severity,
        )

    # ------------------------------------------------------------------
    # Scheduled jobs
    # ------------------------------------------------------------------

    async def _check_training_overdue(self, pool: asyncpg.Pool) -> None:
        logger.info("EscalationEngine: checking overdue training assignments…")
        tenants = await self._get_active_tenants(pool)
        total_inserted = 0

        for tenant_id in tenants:
            async with pool.acquire() as conn, conn.transaction():
                # Set tenant context for querying (for RLS if enabled)
                await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
                overdue_rows = await conn.fetch(
                    """
                    SELECT ta.id, ta.employee_id, tc.title
                    FROM training_assignments ta
                    JOIN training_courses tc
                        ON tc.id = ta.course_id::uuid AND tc.tenant_id = ta.tenant_id
                    WHERE ta.tenant_id = $1
                      AND ta.status IN ('assigned','in_progress','overdue')
                      AND ta.due_date < CURRENT_DATE
                    """,
                    tenant_id,
                )

                for row in overdue_rows:
                    ref_id = str(row["id"])
                    emp_id = row["employee_id"]
                    exists = await self._escalation_exists(
                        conn, tenant_id, emp_id, ref_id, "training_overdue"
                    )
                    if not exists:
                        await self._insert_escalation(
                            conn,
                            tenant_id,
                            emp_id,
                            "training_overdue",
                            ref_id,
                            f"Overdue training assignment: {row['title']}",
                            severity="medium",
                        )
                        total_inserted += 1

        logger.info("EscalationEngine: inserted %d training escalations.", total_inserted)

    async def _check_policy_overdue(self, pool: asyncpg.Pool) -> None:
        logger.info("EscalationEngine: checking overdue policy acknowledgments…")
        tenants = await self._get_active_tenants(pool)
        total_inserted = 0

        for tenant_id in tenants:
            async with pool.acquire() as conn, conn.transaction():
                await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
                overdue_rows = await conn.fetch(
                    """
                    SELECT
                        e.employee_id,
                        p.id        AS policy_id,
                        p.title     AS policy_title,
                        MAX(pa.acknowledged_at) AS last_acked_at
                    FROM employees e
                    CROSS JOIN policies p
                    LEFT JOIN policy_acknowledgments pa
                        ON pa.tenant_id    = e.tenant_id
                        AND pa.policy_id   = p.id::text
                        AND pa.employee_id = e.employee_id
                    WHERE e.tenant_id = $1
                      AND e.employment_status = 'active'
                      AND p.tenant_id = $1
                      AND p.is_active = TRUE
                      AND p.acknowledgment_required = TRUE
                      AND (
                            'all' = ANY(p.applies_to_roles)
                            OR e.job_role = ANY(p.applies_to_roles)
                      )
                    GROUP BY e.employee_id, p.id, p.title, p.acknowledgment_frequency_days
                    HAVING
                        MAX(pa.acknowledged_at) IS NULL
                        OR MAX(pa.acknowledged_at) < NOW() - (p.acknowledgment_frequency_days || ' days')::INTERVAL
                    """,
                    tenant_id,
                )

                for row in overdue_rows:
                    emp_id = row["employee_id"]
                    ref_id = str(row["policy_id"])
                    exists = await self._escalation_exists(
                        conn, tenant_id, emp_id, ref_id, "policy_acknowledgment_overdue"
                    )
                    if not exists:
                        await self._insert_escalation(
                            conn,
                            tenant_id,
                            emp_id,
                            "policy_acknowledgment_overdue",
                            ref_id,
                            f"Overdue policy acknowledgment: {row['policy_title']}",
                            severity="medium",
                        )
                        total_inserted += 1

        logger.info("EscalationEngine: inserted %d policy escalations.", total_inserted)

    async def _check_bgcheck_expiry(self, pool: asyncpg.Pool) -> None:
        logger.info("EscalationEngine: checking background check expiry…")
        tenants = await self._get_active_tenants(pool)
        total_inserted = 0
        warning_days = self.settings.background_check_expiry_warning_days

        for tenant_id in tenants:
            async with pool.acquire() as conn, conn.transaction():
                await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
                expiry_rows = await conn.fetch(
                    """
                    SELECT bc.id, bc.employee_id, bc.check_type, bc.expiry_date
                    FROM background_checks bc
                    JOIN employees e ON e.tenant_id=bc.tenant_id AND e.employee_id=bc.employee_id
                    WHERE bc.tenant_id = $1
                      AND e.employment_status = 'active'
                      AND bc.expiry_date IS NOT NULL
                      AND bc.expiry_date <= CURRENT_DATE + ($2 || ' days')::INTERVAL
                    """,
                    tenant_id,
                    str(warning_days),
                )

                for row in expiry_rows:
                    emp_id = row["employee_id"]
                    ref_id = str(row["id"])
                    is_expired = row["expiry_date"] < datetime.now(tz=timezone.utc).date()
                    esc_type = "background_check_expired" if is_expired else "background_check_expiring"
                    severity = "high" if is_expired else "low"
                    desc = (
                        f"Background check ({row['check_type']}) "
                        + ("has expired" if is_expired else f"expires on {row['expiry_date']}")
                    )
                    exists = await self._escalation_exists(
                        conn, tenant_id, emp_id, ref_id, esc_type
                    )
                    if not exists:
                        await self._insert_escalation(
                            conn,
                            tenant_id,
                            emp_id,
                            esc_type,
                            ref_id,
                            desc,
                            severity=severity,
                        )
                        total_inserted += 1

        logger.info("EscalationEngine: inserted %d background-check escalations.", total_inserted)

    # ------------------------------------------------------------------
    # Manual trigger (used by /escalations/run endpoint)
    # ------------------------------------------------------------------

    async def run_all(self, pool: asyncpg.Pool) -> dict:
        await self._check_training_overdue(pool)
        await self._check_policy_overdue(pool)
        await self._check_bgcheck_expiry(pool)
        return {"status": "completed", "message": "All escalation checks executed."}
