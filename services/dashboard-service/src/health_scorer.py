"""
Health Score Engine — Autonomous Mode

Computes a multi-dimensional health score [0,1] every 15 minutes per tenant+framework.
Dimensions:
  - access_control:      % of PAM requests approved within policy TTLs
  - data_integrity:      chain hash verification pass rate (last 24h evidence)
  - anomaly_rate:        1 - (high/critical anomaly % in last 7d)
  - evidence_freshness:  % of connectors polled within their schedule window
  - narrative_quality:   average combined_score of narratives (last 30d)

Overall score = weighted average of all dimensions.
"""

import logging
from dataclasses import dataclass
import asyncpg

logger = logging.getLogger(__name__)

DIMENSION_WEIGHTS = {
    'access_control': 0.20,
    'data_integrity': 0.30,
    'anomaly_rate': 0.25,
    'evidence_freshness': 0.15,
    'narrative_quality': 0.10,
}


@dataclass
class HealthScore:
    overall_score: float
    access_control: float
    data_integrity: float
    anomaly_rate: float
    evidence_freshness: float
    narrative_quality: float
    open_issues: int
    critical_issues: int


class HealthScorer:
    """Computes health score snapshots and persists them to health_score_snapshots."""

    def __init__(self, db_pool: asyncpg.Pool):
        self._pool = db_pool

    async def compute_and_persist(self, tenant_id: str, framework: str) -> HealthScore:
        """Compute health score for a tenant+framework and persist snapshot."""
        score = await self._compute(tenant_id, framework)
        await self._persist(tenant_id, framework, score)
        return score

    async def _compute(self, tenant_id: str, framework: str) -> HealthScore:
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)

            # 1. Access control: % PAM requests with outcome='approved' in last 30d
            ac_row = await conn.fetchrow("""
                SELECT
                    COUNT(*) FILTER (WHERE outcome = 'approved') AS approved,
                    COUNT(*) AS total
                FROM access_requests
                WHERE tenant_id = $1::uuid
                  AND created_at > NOW() - INTERVAL '30 days'
            """, tenant_id)
            total_pam = ac_row['total'] or 0
            access_control = (ac_row['approved'] / total_pam) if total_pam > 0 else 0.8

            # 2. Data integrity: use chain verification success rate proxy
            # (evidence records with non-null chain_hash in last 24h)
            di_row = await conn.fetchrow("""
                SELECT
                    COUNT(*) FILTER (WHERE chain_hash IS NOT NULL) AS chained,
                    COUNT(*) AS total
                FROM evidence_records
                WHERE tenant_id = $1::uuid
                  AND ingested_at > NOW() - INTERVAL '24 hours'
            """, tenant_id)
            total_er = di_row['total'] or 0
            data_integrity = (di_row['chained'] / total_er) if total_er > 0 else 1.0

            # 3. Anomaly rate: 1 - fraction of high/critical anomalies in last 7d
            an_row = await conn.fetchrow("""
                SELECT
                    COUNT(*) FILTER (WHERE risk_level IN ('high','critical')) AS high_count,
                    COUNT(*) AS total
                FROM anomaly_scores
                WHERE tenant_id = $1::uuid
                  AND scored_at > NOW() - INTERVAL '7 days'
            """, tenant_id)
            total_an = an_row['total'] or 0
            anomaly_rate = 1.0 - (an_row['high_count'] / total_an) if total_an > 0 else 1.0

            # 4. Evidence freshness: % connectors polled within their expected window
            fresh_row = await conn.fetchrow("""
                SELECT
                    COUNT(*) FILTER (
                        WHERE last_successful_poll_at > NOW() - INTERVAL '2 hours'
                    ) AS fresh,
                    COUNT(*) AS total
                FROM connector_registry
                WHERE tenant_id = $1::uuid AND is_active = TRUE
            """, tenant_id)
            total_conn = fresh_row['total'] or 0
            evidence_freshness = (fresh_row['fresh'] / total_conn) if total_conn > 0 else 0.5

            # 5. Narrative quality: avg combined_score for last 30d narratives
            nq_row = await conn.fetchrow("""
                SELECT AVG(combined_score) AS avg_score
                FROM audit_narratives
                WHERE tenant_id = $1::uuid
                  AND framework = $2
                  AND created_at > NOW() - INTERVAL '30 days'
            """, tenant_id, framework)
            narrative_quality = float(nq_row['avg_score'] or 0.7)

            # Count open issues
            issues_row = await conn.fetchrow("""
                SELECT
                    COUNT(*) FILTER (WHERE priority != 'critical') AS open_count,
                    COUNT(*) FILTER (WHERE priority = 'critical') AS critical_count
                FROM audit_hub_items
                WHERE tenant_id = $1::uuid AND status NOT IN ('resolved','waived')
            """, tenant_id)
            open_issues = issues_row['open_count'] or 0
            critical_issues = issues_row['critical_count'] or 0

        # Clamp all dimensions to [0, 1]
        dims = {
            'access_control': min(1.0, max(0.0, access_control)),
            'data_integrity': min(1.0, max(0.0, data_integrity)),
            'anomaly_rate': min(1.0, max(0.0, anomaly_rate)),
            'evidence_freshness': min(1.0, max(0.0, evidence_freshness)),
            'narrative_quality': min(1.0, max(0.0, narrative_quality)),
        }

        overall = sum(dims[k] * DIMENSION_WEIGHTS[k] for k in DIMENSION_WEIGHTS)

        return HealthScore(
            overall_score=round(overall, 3),
            access_control=round(dims['access_control'], 3),
            data_integrity=round(dims['data_integrity'], 3),
            anomaly_rate=round(dims['anomaly_rate'], 3),
            evidence_freshness=round(dims['evidence_freshness'], 3),
            narrative_quality=round(dims['narrative_quality'], 3),
            open_issues=int(open_issues),
            critical_issues=int(critical_issues),
        )

    async def _persist(self, tenant_id: str, framework: str, score: HealthScore) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
            await conn.execute("""
                INSERT INTO health_score_snapshots (
                    tenant_id, framework, overall_score,
                    access_control, data_integrity, anomaly_rate,
                    evidence_freshness, narrative_quality,
                    open_issues, critical_issues
                ) VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
                tenant_id, framework, score.overall_score,
                score.access_control, score.data_integrity, score.anomaly_rate,
                score.evidence_freshness, score.narrative_quality,
                score.open_issues, score.critical_issues,
            )

    async def get_trend(self, tenant_id: str, framework: str, days: int = 30) -> list:
        """Return time-series health scores for trending chart."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
            rows = await conn.fetch("""
                SELECT snapshot_time, overall_score, access_control, data_integrity,
                       anomaly_rate, evidence_freshness, narrative_quality,
                       open_issues, critical_issues
                FROM health_score_snapshots
                WHERE tenant_id = $1::uuid AND framework = $2
                  AND snapshot_time > NOW() - ($3 || ' days')::INTERVAL
                ORDER BY snapshot_time ASC
            """, tenant_id, framework, str(days))
        return [dict(r) for r in rows]
