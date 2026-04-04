import logging
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncpg

from src.models import SyncRequest

logger = logging.getLogger(__name__)


def _parse_cron_hours(cron_expr: str) -> int:
    """
    Simple heuristic: extract the hour interval from a cron expression.
    Handles patterns like:
      "0 */6 * * *"  → 6 hours
      "0 * * * *"    → 1 hour
      "*/30 * * * *" → returns 0 (< 1 hour, treat as 1 hour)
    Returns hours (minimum 1).
    """
    try:
        parts = cron_expr.strip().split()
        if len(parts) < 2:
            return 6
        hour_field = parts[1]
        if hour_field.startswith("*/"):
            interval = int(hour_field[2:])
            return max(1, interval)
        if hour_field == "*":
            return 1
        return 6
    except Exception:
        return 6


class IntegrationScheduler:
    def __init__(self, settings):
        self.scheduler = AsyncIOScheduler()
        self.settings = settings

    def start(self, pool: asyncpg.Pool, sync_engine) -> None:
        if self.settings.sync_schedule_enabled:
            self.scheduler.add_job(
                self._check_due_syncs,
                "interval",
                minutes=15,
                args=[pool, sync_engine],
                id="check_due_syncs",
                replace_existing=True,
            )
            self.scheduler.start()
            logger.info("IntegrationScheduler started (check every 15 minutes)")

    async def _check_due_syncs(self, pool: asyncpg.Pool, sync_engine) -> None:
        logger.info("Scheduler: checking for integrations due for sync")
        now = datetime.now(timezone.utc)

        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, tenant_id, sync_schedule, last_sync_at
                    FROM tenant_integrations
                    WHERE status = 'active'
                    """
                )
        except Exception as exc:
            logger.error("Scheduler: failed to query integrations: %s", exc)
            return

        for row in rows:
            integration_id = str(row["id"])
            tenant_id = str(row["tenant_id"])
            sync_schedule = row["sync_schedule"] or "0 */6 * * *"
            last_sync_at = row["last_sync_at"]

            interval_hours = _parse_cron_hours(sync_schedule)
            due = last_sync_at is None or (
                now - last_sync_at.replace(tzinfo=timezone.utc)
                >= timedelta(hours=interval_hours)
            )

            if due:
                logger.info(
                    "Scheduler: triggering sync for integration %s (tenant %s)",
                    integration_id,
                    tenant_id,
                )
                try:
                    await sync_engine.run_sync(
                        pool,
                        tenant_id,
                        integration_id,
                        SyncRequest(sync_type="scheduled"),
                    )
                except Exception as exc:
                    logger.error(
                        "Scheduler: sync failed for integration %s: %s",
                        integration_id,
                        exc,
                    )

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("IntegrationScheduler stopped")
