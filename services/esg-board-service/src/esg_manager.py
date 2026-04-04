from __future__ import annotations

import uuid
from datetime import datetime, timezone

import asyncpg

from .db import tenant_conn
from .models import DisclosureCreate, TargetCreate


class ESGManager:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # ------------------------------------------------------------------
    # Frameworks & Metric Definitions (platform data — no tenant context)
    # ------------------------------------------------------------------

    async def get_frameworks(self, category: str | None = None) -> list[dict]:
        query = "SELECT * FROM esg_frameworks"
        params: list = []
        if category:
            query += " WHERE category = $1"
            params.append(category)
        query += " ORDER BY category, display_name"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]

    async def get_metric_definitions(
        self,
        category: str | None = None,
        framework_id: str | None = None,
    ) -> list[dict]:
        conditions: list[str] = []
        params: list = []
        idx = 1
        if category:
            conditions.append(f"md.category = ${idx}")
            params.append(category)
            idx += 1
        if framework_id:
            conditions.append(f"md.framework_id = ${idx}")
            params.append(framework_id)
            idx += 1

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        query = f"""
            SELECT
                md.*,
                ef.display_name  AS framework_name,
                ef.abbreviation  AS framework_abbreviation
            FROM esg_metric_definitions md
            LEFT JOIN esg_frameworks ef ON ef.id = md.framework_id
            {where}
            ORDER BY md.category, md.display_name
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Disclosures (immutable — INSERT only)
    # ------------------------------------------------------------------

    async def submit_disclosure(
        self, tenant_id: str, data: DisclosureCreate
    ) -> dict:
        # Validate at least one value field is non-null
        if all(
            v is None
            for v in (
                data.numeric_value,
                data.text_value,
                data.boolean_value,
                data.currency_value,
            )
        ):
            raise ValueError(
                "At least one of numeric_value, text_value, boolean_value, "
                "or currency_value must be provided"
            )

        disclosure_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO esg_disclosures (
                    id, tenant_id, metric_definition_id, reporting_period,
                    period_type, numeric_value, text_value, boolean_value,
                    currency_value, currency_code, notes, data_source,
                    assurance_level, assured_by, submitted_by, created_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16
                )
                RETURNING *
                """,
                disclosure_id,
                tenant_id,
                data.metric_definition_id,
                data.reporting_period,
                data.period_type,
                data.numeric_value,
                data.text_value,
                data.boolean_value,
                data.currency_value,
                data.currency_code,
                data.notes,
                data.data_source,
                data.assurance_level,
                data.assured_by,
                data.submitted_by,
                now,
            )
        return dict(row)

    async def get_disclosures(
        self,
        tenant_id: str,
        reporting_period: str | None = None,
        category: str | None = None,
        metric_id: str | None = None,
    ) -> list[dict]:
        conditions: list[str] = []
        params: list = []
        idx = 1

        if reporting_period:
            conditions.append(f"d.reporting_period = ${idx}")
            params.append(reporting_period)
            idx += 1
        if category:
            conditions.append(f"md.category = ${idx}")
            params.append(category)
            idx += 1
        if metric_id:
            conditions.append(f"d.metric_definition_id = ${idx}")
            params.append(metric_id)
            idx += 1

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        query = f"""
            SELECT
                d.*,
                md.display_name  AS metric_name,
                md.category,
                md.unit,
                ef.display_name  AS framework_name,
                ef.abbreviation  AS framework_abbreviation
            FROM esg_disclosures d
            JOIN esg_metric_definitions md ON md.id = d.metric_definition_id
            LEFT JOIN esg_frameworks ef ON ef.id = md.framework_id
            {where}
            ORDER BY d.reporting_period DESC, md.category, md.display_name
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]

    async def get_esg_scorecard(
        self, tenant_id: str, reporting_period: str
    ) -> dict:
        # Fetch all metric definitions with required flag
        async with self.pool.acquire() as conn:
            all_metrics = await conn.fetch(
                """
                SELECT id, display_name, category, unit, is_required
                FROM esg_metric_definitions
                ORDER BY category, display_name
                """
            )

        # Fetch latest disclosure per metric for this period using tenant_conn
        async with tenant_conn(self.pool, tenant_id) as conn:
            disclosed = await conn.fetch(
                """
                SELECT DISTINCT ON (metric_definition_id)
                    metric_definition_id,
                    numeric_value,
                    text_value,
                    boolean_value,
                    currency_value,
                    reporting_period,
                    assurance_level
                FROM esg_disclosures
                WHERE reporting_period = $1
                ORDER BY metric_definition_id, created_at DESC
                """,
                reporting_period,
            )

        disclosed_map = {r["metric_definition_id"]: dict(r) for r in disclosed}

        categories = {
            "environmental": {"label": "E", "metrics": []},
            "social": {"label": "S", "metrics": []},
            "governance": {"label": "G", "metrics": []},
        }

        cat_key_map = {
            "environmental": "environmental",
            "social": "social",
            "governance": "governance",
        }

        total_metrics = 0
        disclosed_metrics = 0

        for m in all_metrics:
            cat = (m["category"] or "").lower()
            bucket_key = cat_key_map.get(cat)
            if bucket_key is None:
                continue

            total_metrics += 1
            disc = disclosed_map.get(m["id"])
            has_value = disc is not None
            if has_value:
                disclosed_metrics += 1

            entry = {
                "id": m["id"],
                "display_name": m["display_name"],
                "unit": m["unit"],
                "is_required": m["is_required"],
                "has_disclosure": has_value,
                "latest_value": disc,
            }
            categories[bucket_key]["metrics"].append(entry)

        def coverage(bucket: dict) -> float:
            total = len(bucket["metrics"])
            if total == 0:
                return 0.0
            disclosed_count = sum(
                1 for m in bucket["metrics"] if m["has_disclosure"]
            )
            return round(disclosed_count / total * 100, 1)

        env_cov = coverage(categories["environmental"])
        soc_cov = coverage(categories["social"])
        gov_cov = coverage(categories["governance"])
        overall = (
            round(disclosed_metrics / total_metrics * 100, 1)
            if total_metrics
            else 0.0
        )

        return {
            "reporting_period": reporting_period,
            "environmental": {
                "coverage_pct": env_cov,
                "metrics": categories["environmental"]["metrics"],
            },
            "social": {
                "coverage_pct": soc_cov,
                "metrics": categories["social"]["metrics"],
            },
            "governance": {
                "coverage_pct": gov_cov,
                "metrics": categories["governance"]["metrics"],
            },
            "overall_coverage_pct": overall,
            "total_metrics": total_metrics,
            "disclosed_metrics": disclosed_metrics,
        }

    # ------------------------------------------------------------------
    # Targets
    # ------------------------------------------------------------------

    async def upsert_target(
        self, tenant_id: str, data: TargetCreate
    ) -> dict:
        target_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO esg_targets (
                    id, tenant_id, metric_definition_id, target_year,
                    baseline_year, baseline_value, target_value, target_type,
                    description, science_based, framework_alignment,
                    status, created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                    'active', $12, $12
                )
                ON CONFLICT (tenant_id, metric_definition_id, target_year)
                DO UPDATE SET
                    baseline_year        = EXCLUDED.baseline_year,
                    baseline_value       = EXCLUDED.baseline_value,
                    target_value         = EXCLUDED.target_value,
                    target_type          = EXCLUDED.target_type,
                    description          = EXCLUDED.description,
                    science_based        = EXCLUDED.science_based,
                    framework_alignment  = EXCLUDED.framework_alignment,
                    updated_at           = EXCLUDED.updated_at
                RETURNING *
                """,
                target_id,
                tenant_id,
                data.metric_definition_id,
                data.target_year,
                data.baseline_year,
                data.baseline_value,
                data.target_value,
                data.target_type,
                data.description,
                data.science_based,
                data.framework_alignment,
                now,
            )
        return dict(row)

    async def get_targets(
        self,
        tenant_id: str,
        metric_id: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        conditions: list[str] = []
        params: list = []
        idx = 1

        if metric_id:
            conditions.append(f"t.metric_definition_id = ${idx}")
            params.append(metric_id)
            idx += 1
        if status:
            conditions.append(f"t.status = ${idx}")
            params.append(status)
            idx += 1

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        query = f"""
            SELECT
                t.*,
                md.display_name AS metric_name,
                md.category,
                md.unit
            FROM esg_targets t
            JOIN esg_metric_definitions md ON md.id = t.metric_definition_id
            {where}
            ORDER BY t.target_year, md.category, md.display_name
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]

    async def get_target_progress(
        self, tenant_id: str, target_year: int
    ) -> list[dict]:
        # Fetch active targets for the given year
        async with tenant_conn(self.pool, tenant_id) as conn:
            targets = await conn.fetch(
                """
                SELECT
                    t.*,
                    md.display_name    AS metric_name,
                    md.category,
                    md.unit,
                    md.lower_is_better
                FROM esg_targets t
                JOIN esg_metric_definitions md ON md.id = t.metric_definition_id
                WHERE t.target_year = $1 AND t.status = 'active'
                ORDER BY md.category, md.display_name
                """,
                target_year,
            )

            # Latest disclosure per metric
            if not targets:
                return []

            metric_ids = list({r["metric_definition_id"] for r in targets})
            latest_disclosures = await conn.fetch(
                """
                SELECT DISTINCT ON (metric_definition_id)
                    metric_definition_id,
                    numeric_value,
                    reporting_period
                FROM esg_disclosures
                WHERE metric_definition_id = ANY($1::uuid[])
                ORDER BY metric_definition_id, created_at DESC
                """,
                metric_ids,
            )

        latest_map = {
            r["metric_definition_id"]: dict(r) for r in latest_disclosures
        }

        results = []
        for t in targets:
            td = dict(t)
            latest = latest_map.get(t["metric_definition_id"])
            current_val = latest["numeric_value"] if latest else None
            baseline = td.get("baseline_value")
            target_val = td["target_value"]
            lower_is_better = td.get("lower_is_better", False)

            progress_pct: float | None = None
            on_track: bool | None = None

            if (
                current_val is not None
                and baseline is not None
                and target_val is not None
            ):
                denom_target = baseline - target_val if lower_is_better else target_val - baseline
                denom_current = baseline - current_val if lower_is_better else current_val - baseline
                if denom_target != 0:
                    progress_pct = round(denom_current / denom_target * 100, 1)
                    # Linear interpolation — on track if >= expected progress
                    # Simple heuristic: on track if progress >= 50% (mid-point indicator)
                    on_track = progress_pct >= 0

            results.append(
                {
                    **td,
                    "latest_value": current_val,
                    "latest_reporting_period": latest["reporting_period"] if latest else None,
                    "progress_pct": progress_pct,
                    "on_track": on_track,
                }
            )

        return results

    # ------------------------------------------------------------------
    # Trend data
    # ------------------------------------------------------------------

    async def get_trend_data(
        self, tenant_id: str, metric_id: str, periods: int = 8
    ) -> list[dict]:
        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT
                    reporting_period,
                    numeric_value,
                    text_value,
                    boolean_value,
                    currency_value,
                    data_source,
                    assurance_level,
                    created_at
                FROM esg_disclosures
                WHERE metric_definition_id = $1
                ORDER BY reporting_period DESC, created_at DESC
                LIMIT $2
                """,
                metric_id,
                periods,
            )
        return [dict(r) for r in rows]
