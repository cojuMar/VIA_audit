import logging
from uuid import UUID

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .models import ChatRequest

logger = logging.getLogger(__name__)


class AgentScheduler:
    def __init__(self, settings):
        self.scheduler = AsyncIOScheduler()
        self.settings = settings

    def start(self, pool, agent_engine):
        """Start the APScheduler and register background jobs."""
        # Every hour: check for due scheduled queries
        self.scheduler.add_job(
            self._run_due_queries,
            "interval",
            hours=1,
            args=[pool, agent_engine],
            id="run_due_queries",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info("AgentScheduler started")

    async def _run_due_queries(self, pool, agent_engine):
        """
        Find all active scheduled queries across all tenants that are due
        to run and execute them via the agent engine.
        """
        try:
            # Use a raw connection outside tenant context to scan across tenants
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT id, tenant_id, natural_language_query, query_name
                       FROM agent_scheduled_queries
                       WHERE is_active = true
                         AND (next_run_at IS NULL OR next_run_at <= NOW())"""
                )

            for row in rows:
                tenant_id = str(row["tenant_id"])
                query_id = str(row["id"])
                try:
                    request = ChatRequest(
                        message=row["natural_language_query"],
                        user_identifier=f"scheduler:{row['query_name']}",
                    )
                    await agent_engine.chat(pool, tenant_id, request)

                    # Update last_run_at and calculate next_run_at
                    async with pool.acquire() as conn:
                        await conn.execute(
                            """UPDATE agent_scheduled_queries
                               SET last_run_at = NOW(),
                                   next_run_at = NOW() + INTERVAL '1 week'
                               WHERE id = $1""",
                            UUID(query_id),
                        )
                    logger.info("Ran scheduled query %s for tenant %s", query_id, tenant_id)
                except Exception as exc:
                    logger.error(
                        "Failed scheduled query %s for tenant %s: %s",
                        query_id, tenant_id, exc
                    )
        except Exception as exc:
            logger.error("Error in _run_due_queries: %s", exc)

    def stop(self):
        """Gracefully shut down the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("AgentScheduler stopped")
