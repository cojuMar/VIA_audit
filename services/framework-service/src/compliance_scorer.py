"""
Compliance Scorer — Computes real-time compliance score per tenant per framework.

Score = (passing_controls / total_applicable_controls) * 100

- not_applicable controls are excluded from denominator
- exception controls count as 0.5 (partial credit)
- Scores are persisted as immutable snapshots in compliance_scores table
- APScheduler refreshes all tenant scores every 30 minutes
"""
import logging
from typing import List, Dict
from uuid import UUID
from datetime import datetime, timezone
from .models import ComplianceScore

logger = logging.getLogger(__name__)


class ComplianceScorer:
    def __init__(self, db_pool):
        self._pool = db_pool

    async def compute_score(self, tenant_id: UUID, framework_id: UUID) -> ComplianceScore:
        """Compute and persist a score snapshot for one tenant+framework."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant_id))

            # Get framework name
            framework_name = await conn.fetchval(
                "SELECT name FROM compliance_frameworks WHERE id = $1", framework_id
            )

            # Count controls by status
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM framework_controls WHERE framework_id = $1", framework_id
            )

            status_counts = await conn.fetch("""
                SELECT
                    COALESCE(tce.status, 'not_started') as status,
                    COUNT(*) as cnt
                FROM framework_controls fc
                LEFT JOIN tenant_control_evidence tce ON (
                    tce.framework_control_id = fc.id AND tce.tenant_id = $1
                )
                WHERE fc.framework_id = $2
                GROUP BY COALESCE(tce.status, 'not_started')
            """, tenant_id, framework_id)

            counts = {row['status']: row['cnt'] for row in status_counts}
            passing = counts.get('passing', 0)
            failing = counts.get('failing', 0)
            not_started = counts.get('not_started', 0) + counts.get('in_progress', 0)
            not_applicable = counts.get('not_applicable', 0)
            exception = counts.get('exception', 0)

            denominator = total - not_applicable
            if denominator == 0:
                score_pct = 100.0
            else:
                effective_passing = passing + (exception * 0.5)
                score_pct = round((effective_passing / denominator) * 100, 2)

            # Persist immutable snapshot
            await conn.execute("""
                INSERT INTO compliance_scores
                    (tenant_id, framework_id, score_pct, passing_controls,
                     failing_controls, not_started_controls, total_controls)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, tenant_id, framework_id, score_pct, passing, failing, not_started, total)

            return ComplianceScore(
                framework_id=framework_id,
                framework_name=framework_name,
                score_pct=score_pct,
                passing_controls=passing,
                failing_controls=failing,
                not_started_controls=not_started,
                total_controls=total,
                computed_at=datetime.now(timezone.utc)
            )

    async def compute_all_tenant_scores(self, tenant_id: UUID) -> List[ComplianceScore]:
        """Compute scores for all active frameworks for a tenant."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant_id))
            frameworks = await conn.fetch("""
                SELECT framework_id FROM tenant_frameworks
                WHERE tenant_id = $1 AND is_active = TRUE
            """, tenant_id)

        scores = []
        for row in frameworks:
            score = await self.compute_score(tenant_id, row['framework_id'])
            scores.append(score)
        return scores

    async def get_latest_scores(self, tenant_id: UUID) -> List[Dict]:
        """Get the most recent score snapshot per framework for a tenant."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant_id))
            rows = await conn.fetch("""
                SELECT DISTINCT ON (cs.framework_id)
                    cs.framework_id, cs.score_pct,
                    cs.passing_controls, cs.failing_controls,
                    cs.not_started_controls, cs.total_controls,
                    cs.computed_at, cf.name as framework_name, cf.slug
                FROM compliance_scores cs
                JOIN compliance_frameworks cf ON cf.id = cs.framework_id
                WHERE cs.tenant_id = $1
                ORDER BY cs.framework_id, cs.computed_at DESC
            """, tenant_id)
            return [dict(r) for r in rows]
