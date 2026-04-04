import logging
import uuid
from datetime import datetime, timezone, timedelta

import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

# Interval labels → timedelta mapping for schedule_interval field
_INTERVAL_MAP: dict[str, timedelta] = {
    "hourly": timedelta(hours=1),
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "monthly": timedelta(days=30),
}


class MonitoringScheduler:
    def __init__(self, settings):
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self.settings = settings

    def start(self, pool: asyncpg.Pool) -> None:
        if self.settings.monitoring_schedule_enabled:
            self.scheduler.add_job(
                self._run_scheduled_checks,
                "cron",
                hour=2,
                minute=0,
                args=[pool],
                id="monitoring_daily_check",
                replace_existing=True,
            )
            self.scheduler.start()
            logger.info("MonitoringScheduler started — daily check at 02:00 UTC")

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("MonitoringScheduler stopped")

    async def _run_scheduled_checks(self, pool: asyncpg.Pool) -> None:
        logger.info("Running scheduled monitoring checks")
        try:
            async with pool.acquire() as conn:
                configs = await conn.fetch(
                    """
                    SELECT id, tenant_id, rule_key, schedule_interval, last_run_at, config_overrides
                    FROM tenant_monitoring_configs
                    WHERE is_enabled = TRUE
                    """
                )
        except Exception as exc:
            logger.error("Failed to fetch monitoring configs: %s", exc)
            return

        now = datetime.now(timezone.utc)

        for cfg in configs:
            try:
                await self._maybe_trigger(pool, cfg, now)
            except Exception as exc:
                logger.error(
                    "Error triggering check for tenant=%s rule=%s: %s",
                    cfg["tenant_id"],
                    cfg["rule_key"],
                    exc,
                )

    async def _maybe_trigger(self, pool: asyncpg.Pool, cfg, now: datetime) -> None:
        interval_str = cfg["schedule_interval"] or "daily"
        interval = _INTERVAL_MAP.get(interval_str, timedelta(days=1))
        last_run = cfg["last_run_at"]

        if last_run is not None:
            # Make timezone-aware for comparison
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=timezone.utc)
            if now - last_run < interval:
                return  # Not due yet

        tenant_id = str(cfg["tenant_id"])
        rule_key = cfg["rule_key"]
        run_id = str(uuid.uuid4())

        logger.info("Triggering scheduled check: tenant=%s rule=%s run_id=%s", tenant_id, rule_key, run_id)

        async with pool.acquire() as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO monitoring_runs
                        (id, tenant_id, rule_key, status, triggered_by, created_at)
                    VALUES ($1, $2, $3, 'scheduled', 'scheduler', NOW())
                    """,
                    run_id,
                    tenant_id,
                    rule_key,
                )
            except Exception as exc:
                logger.error("Failed to insert monitoring_run: %s", exc)
                return

            # Update last_run_at on the config record
            try:
                await conn.execute(
                    """
                    UPDATE tenant_monitoring_configs
                    SET last_run_at = NOW()
                    WHERE tenant_id = $1 AND rule_key = $2
                    """,
                    tenant_id,
                    rule_key,
                )
            except Exception as exc:
                logger.warning("Could not update last_run_at: %s", exc)
