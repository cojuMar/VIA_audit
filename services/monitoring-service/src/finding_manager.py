import logging
from datetime import datetime, timezone

import asyncpg

from .db import tenant_conn
from .models import MonitoringFinding

logger = logging.getLogger(__name__)


class FindingManager:
    async def save_findings(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        run_id: str,
        rule_id: str | None,
        findings: list[MonitoringFinding],
    ) -> int:
        if not findings:
            return 0
        count = 0
        async with tenant_conn(pool, tenant_id) as conn:
            for f in findings:
                try:
                    await conn.execute(
                        """
                        INSERT INTO monitoring_findings
                            (tenant_id, run_id, rule_id,
                             finding_type, severity, title, description,
                             entity_type, entity_id, entity_name,
                             evidence, risk_score, status, detected_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'open',NOW())
                        """,
                        tenant_id,
                        run_id,
                        rule_id,
                        f.finding_type,
                        f.severity,
                        f.title,
                        f.description,
                        f.entity_type,
                        f.entity_id,
                        f.entity_name,
                        f.evidence,
                        f.risk_score,
                    )
                    count += 1
                except Exception as exc:
                    logger.error("Failed to save finding: %s", exc)
        return count

    async def get_findings(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        severity: str | None = None,
        finding_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        conditions = ["tenant_id = $1"]
        params: list = [tenant_id]
        idx = 2

        if severity:
            conditions.append(f"severity = ${idx}")
            params.append(severity)
            idx += 1
        if finding_type:
            conditions.append(f"finding_type = ${idx}")
            params.append(finding_type)
            idx += 1
        if status:
            conditions.append(f"status = ${idx}")
            params.append(status)
            idx += 1

        where_clause = " AND ".join(conditions)
        params.append(limit)

        query = f"""
            SELECT id, tenant_id, run_id, rule_id,
                   finding_type, severity, title, description,
                   entity_type, entity_id, entity_name,
                   evidence, risk_score, status, detected_at
            FROM monitoring_findings
            WHERE {where_clause}
            ORDER BY detected_at DESC
            LIMIT ${idx}
        """

        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(query, *params)

        return [dict(row) for row in rows]

    async def get_finding_by_id(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        finding_id: str,
    ) -> dict | None:
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT id, tenant_id, run_id, rule_id,
                       finding_type, severity, title, description,
                       entity_type, entity_id, entity_name,
                       evidence, risk_score, status, detected_at
                FROM monitoring_findings
                WHERE tenant_id = $1 AND id = $2
                """,
                tenant_id,
                finding_id,
            )
        return dict(row) if row else None

    async def get_findings_summary(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            total_row = await conn.fetchrow(
                "SELECT COUNT(*) AS total FROM monitoring_findings WHERE tenant_id = $1",
                tenant_id,
            )
            severity_rows = await conn.fetch(
                """
                SELECT severity, COUNT(*) AS cnt
                FROM monitoring_findings
                WHERE tenant_id = $1
                GROUP BY severity
                """,
                tenant_id,
            )
            type_rows = await conn.fetch(
                """
                SELECT finding_type, COUNT(*) AS cnt
                FROM monitoring_findings
                WHERE tenant_id = $1
                GROUP BY finding_type
                ORDER BY cnt DESC
                LIMIT 20
                """,
                tenant_id,
            )
            open_row = await conn.fetchrow(
                "SELECT COUNT(*) AS cnt FROM monitoring_findings WHERE tenant_id = $1 AND status = 'open'",
                tenant_id,
            )
            last_run_row = await conn.fetchrow(
                """
                SELECT MAX(detected_at) AS last_run_at
                FROM monitoring_runs
                WHERE tenant_id = $1 AND status = 'completed'
                """,
                tenant_id,
            )

        by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for row in severity_rows:
            sev = row["severity"]
            if sev in by_severity:
                by_severity[sev] = row["cnt"]

        by_type = {row["finding_type"]: row["cnt"] for row in type_rows}

        return {
            "total": total_row["total"] if total_row else 0,
            "by_severity": by_severity,
            "by_type": by_type,
            "open_count": open_row["cnt"] if open_row else 0,
            "last_run_at": last_run_row["last_run_at"].isoformat() if last_run_row and last_run_row["last_run_at"] else None,
        }

    async def get_trend_data(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        days: int = 30,
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT
                    DATE(detected_at) AS date,
                    severity,
                    COUNT(*) AS cnt
                FROM monitoring_findings
                WHERE tenant_id = $1
                  AND detected_at >= NOW() - ($2 || ' days')::INTERVAL
                GROUP BY DATE(detected_at), severity
                ORDER BY date
                """,
                tenant_id,
                str(days),
            )

        # Pivot into daily rows
        daily: dict[str, dict] = {}
        for row in rows:
            date_str = row["date"].isoformat()
            if date_str not in daily:
                daily[date_str] = {"date": date_str, "critical": 0, "high": 0, "medium": 0, "low": 0}
            sev = row["severity"]
            if sev in daily[date_str]:
                daily[date_str][sev] = row["cnt"]

        return sorted(daily.values(), key=lambda x: x["date"])
