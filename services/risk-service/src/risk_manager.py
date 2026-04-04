from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone

import asyncpg

from .db import tenant_conn
from .models import AssessmentCreate, RiskCreate, RiskUpdate
from .risk_scorer import RiskScorer

logger = logging.getLogger(__name__)

_scorer = RiskScorer()

# Mapping finding_type prefixes -> category_key
_FINDING_TYPE_TO_CATEGORY: dict[str, str] = {
    "payroll": "financial",
    "invoice": "financial",
    "card": "financial",
    "sod": "compliance",
    "cloud": "cybersecurity",
}


def _row_to_dict(row: asyncpg.Record) -> dict:
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, (datetime,)):
            d[k] = v.isoformat()
        elif isinstance(v, date):
            d[k] = v.isoformat()
    return d


class RiskManager:
    # ------------------------------------------------------------------
    # create
    # ------------------------------------------------------------------
    async def create(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        data: RiskCreate,
        auto_source_id: str | None = None,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            # 1. Look up category_id (platform table — no tenant filter)
            cat_row = await conn.fetchrow(
                "SELECT id, name FROM risk_categories WHERE category_key = $1",
                data.category_key,
            )
            if not cat_row:
                raise ValueError(f"Unknown category_key: {data.category_key}")
            category_id = cat_row["id"]
            category_name = cat_row["name"]

            risk_uuid = str(uuid.uuid4())
            inherent_score = _scorer.score(data.inherent_likelihood, data.inherent_impact)
            residual_score: float | None = None
            if data.residual_likelihood is not None and data.residual_impact is not None:
                residual_score = _scorer.score(
                    data.residual_likelihood, data.residual_impact
                )
            target_score: float | None = None
            if data.target_likelihood is not None and data.target_impact is not None:
                target_score = _scorer.score(data.target_likelihood, data.target_impact)

            # 2. INSERT risk record
            await conn.execute(
                """
                INSERT INTO risks (
                    id, tenant_id, risk_id, title, description,
                    category_id, owner, department,
                    inherent_likelihood, inherent_impact, inherent_score,
                    residual_likelihood, residual_impact, residual_score,
                    target_likelihood, target_impact, target_score,
                    framework_control_refs, source, auto_source_id,
                    identified_date, review_date, status, created_at, updated_at
                ) VALUES (
                    $1,$2,$3,$4,$5,
                    $6,$7,$8,
                    $9,$10,$11,
                    $12,$13,$14,
                    $15,$16,$17,
                    $18,$19,$20,
                    $21,$22,'open',NOW(),NOW()
                )
                """,
                risk_uuid,
                tenant_id,
                data.risk_id,
                data.title,
                data.description,
                category_id,
                data.owner,
                data.department,
                data.inherent_likelihood,
                data.inherent_impact,
                inherent_score,
                data.residual_likelihood,
                data.residual_impact,
                residual_score,
                data.target_likelihood,
                data.target_impact,
                target_score,
                data.framework_control_refs,
                data.source,
                auto_source_id,
                data.identified_date,
                data.review_date,
            )

            # 3. INSERT initial risk_score_history (immutable)
            await conn.execute(
                """
                INSERT INTO risk_score_history (
                    id, tenant_id, risk_id,
                    inherent_likelihood, inherent_impact, inherent_score,
                    residual_likelihood, residual_impact, residual_score,
                    change_reason, changed_by, recorded_at
                ) VALUES (
                    $1,$2,$3,
                    $4,$5,$6,
                    $7,$8,$9,
                    'initial_assessment','system',NOW()
                )
                """,
                str(uuid.uuid4()),
                tenant_id,
                risk_uuid,
                data.inherent_likelihood,
                data.inherent_impact,
                inherent_score,
                data.residual_likelihood,
                data.residual_impact,
                residual_score,
            )

            # 4. Return risk dict with category name
            row = await conn.fetchrow(
                "SELECT * FROM risks WHERE id = $1 AND tenant_id = $2",
                risk_uuid,
                tenant_id,
            )
            result = _row_to_dict(row)
            result["category_name"] = category_name
            return result

    # ------------------------------------------------------------------
    # update
    # ------------------------------------------------------------------
    async def update(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        risk_uuid: str,
        data: RiskUpdate,
        changed_by: str = "api",
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            existing = await conn.fetchrow(
                "SELECT * FROM risks WHERE id = $1 AND tenant_id = $2",
                risk_uuid,
                tenant_id,
            )
            if not existing:
                raise LookupError(f"Risk not found: {risk_uuid}")

            sets: list[str] = []
            params: list = []
            idx = 1

            field_map = {
                "title": data.title,
                "description": data.description,
                "owner": data.owner,
                "department": data.department,
                "status": data.status,
                "residual_likelihood": data.residual_likelihood,
                "residual_impact": data.residual_impact,
                "target_likelihood": data.target_likelihood,
                "target_impact": data.target_impact,
                "review_date": data.review_date,
            }
            for col, val in field_map.items():
                if val is not None:
                    sets.append(f"{col} = ${idx}")
                    params.append(val)
                    idx += 1

            # Recompute derived scores if residual or target changed
            new_residual_l = data.residual_likelihood or existing["residual_likelihood"]
            new_residual_i = data.residual_impact or existing["residual_impact"]
            new_target_l = data.target_likelihood or existing["target_likelihood"]
            new_target_i = data.target_impact or existing["target_impact"]

            score_changed = False
            if data.residual_likelihood is not None or data.residual_impact is not None:
                if new_residual_l is not None and new_residual_i is not None:
                    new_residual_score = _scorer.score(new_residual_l, new_residual_i)
                    sets.append(f"residual_score = ${idx}")
                    params.append(new_residual_score)
                    idx += 1
                    score_changed = True

            if data.target_likelihood is not None or data.target_impact is not None:
                if new_target_l is not None and new_target_i is not None:
                    new_target_score = _scorer.score(new_target_l, new_target_i)
                    sets.append(f"target_score = ${idx}")
                    params.append(new_target_score)
                    idx += 1

            if sets:
                sets.append(f"updated_at = NOW()")
                params += [tenant_id, risk_uuid]
                await conn.execute(
                    f"UPDATE risks SET {', '.join(sets)} "
                    f"WHERE tenant_id = ${idx} AND id = ${idx + 1}",
                    *params,
                )

            # If score changed: INSERT risk_score_history (immutable)
            if score_changed and new_residual_l is not None and new_residual_i is not None:
                new_residual_score = _scorer.score(new_residual_l, new_residual_i)
                await conn.execute(
                    """
                    INSERT INTO risk_score_history (
                        id, tenant_id, risk_id,
                        inherent_likelihood, inherent_impact, inherent_score,
                        residual_likelihood, residual_impact, residual_score,
                        change_reason, changed_by, recorded_at
                    ) VALUES (
                        $1,$2,$3,
                        $4,$5,$6,
                        $7,$8,$9,
                        'score_update',$10,NOW()
                    )
                    """,
                    str(uuid.uuid4()),
                    tenant_id,
                    risk_uuid,
                    existing["inherent_likelihood"],
                    existing["inherent_impact"],
                    existing["inherent_score"],
                    new_residual_l,
                    new_residual_i,
                    new_residual_score,
                    changed_by,
                )

            updated = await conn.fetchrow(
                """
                SELECT r.*, rc.display_name AS category_name
                FROM risks r
                LEFT JOIN risk_categories rc ON rc.id = r.category_id
                WHERE r.id = $1 AND r.tenant_id = $2
                """,
                risk_uuid,
                tenant_id,
            )
            return _row_to_dict(updated)

    # ------------------------------------------------------------------
    # list
    # ------------------------------------------------------------------
    async def list(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        status: str | None = None,
        category_key: str | None = None,
        min_score: float | None = None,
        limit: int = 100,
    ) -> list[dict]:
        conditions = ["r.tenant_id = $1"]
        params: list = [tenant_id]
        idx = 2

        if status:
            conditions.append(f"r.status = ${idx}")
            params.append(status)
            idx += 1
        if category_key:
            conditions.append(f"rc.category_key = ${idx}")
            params.append(category_key)
            idx += 1
        if min_score is not None:
            conditions.append(
                f"COALESCE(r.residual_score, r.inherent_score) >= ${idx}"
            )
            params.append(min_score)
            idx += 1

        params.append(limit)
        where = " AND ".join(conditions)

        query = f"""
            SELECT r.*, rc.display_name AS category_name, rc.category_key AS category_key_out
            FROM risks r
            LEFT JOIN risk_categories rc ON rc.id = r.category_id
            WHERE {where}
            ORDER BY COALESCE(r.residual_score, r.inherent_score) DESC
            LIMIT ${idx}
        """

        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(query, *params)

        return [_row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # get (full detail)
    # ------------------------------------------------------------------
    async def get(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        risk_uuid: str,
    ) -> dict | None:
        async with tenant_conn(pool, tenant_id) as conn:
            risk_row = await conn.fetchrow(
                """
                SELECT r.*, rc.display_name AS category_name, rc.category_key AS category_key_out
                FROM risks r
                LEFT JOIN risk_categories rc ON rc.id = r.category_id
                WHERE r.id = $1 AND r.tenant_id = $2
                """,
                risk_uuid,
                tenant_id,
            )
            if not risk_row:
                return None

            # Treatments
            treatment_rows = await conn.fetch(
                """
                SELECT * FROM risk_treatments
                WHERE risk_id = $1 AND tenant_id = $2
                ORDER BY created_at
                """,
                risk_uuid,
                tenant_id,
            )

            # Latest assessment
            assessment_row = await conn.fetchrow(
                """
                SELECT * FROM risk_assessments
                WHERE risk_id = $1 AND tenant_id = $2
                ORDER BY assessed_at DESC
                LIMIT 1
                """,
                risk_uuid,
                tenant_id,
            )

            # Indicators
            indicator_rows = await conn.fetch(
                """
                SELECT ri.*,
                       (SELECT value FROM risk_indicator_readings rir
                        WHERE rir.indicator_id = ri.id
                        ORDER BY rir.recorded_at DESC LIMIT 1) AS latest_value,
                       (SELECT recorded_at FROM risk_indicator_readings rir
                        WHERE rir.indicator_id = ri.id
                        ORDER BY rir.recorded_at DESC LIMIT 1) AS latest_reading_at
                FROM risk_indicators ri
                WHERE ri.risk_id = $1 AND ri.tenant_id = $2
                ORDER BY ri.created_at
                """,
                risk_uuid,
                tenant_id,
            )

        result = _row_to_dict(risk_row)
        result["treatments"] = [_row_to_dict(r) for r in treatment_rows]
        result["latest_assessment"] = _row_to_dict(assessment_row) if assessment_row else None
        result["indicators"] = [_row_to_dict(r) for r in indicator_rows]

        # Enrich with score labels/colors
        il = result.get("inherent_likelihood") or 0
        ii = result.get("inherent_impact") or 0
        result["inherent_score_label"] = _scorer.label(il, ii)
        result["inherent_score_color"] = _scorer.color(il, ii)

        rl = result.get("residual_likelihood")
        ri = result.get("residual_impact")
        if rl and ri:
            result["residual_score_label"] = _scorer.label(rl, ri)
            result["residual_score_color"] = _scorer.color(rl, ri)
            result["risk_reduction_pct"] = _scorer.risk_reduction(il, ii, rl, ri)

        return result

    # ------------------------------------------------------------------
    # close
    # ------------------------------------------------------------------
    async def close(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        risk_uuid: str,
        reason: str,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            existing = await conn.fetchrow(
                "SELECT id FROM risks WHERE id = $1 AND tenant_id = $2",
                risk_uuid,
                tenant_id,
            )
            if not existing:
                raise LookupError(f"Risk not found: {risk_uuid}")

            await conn.execute(
                """
                UPDATE risks
                SET status = 'closed',
                    closed_date = CURRENT_DATE,
                    close_reason = $1,
                    updated_at = NOW()
                WHERE id = $2 AND tenant_id = $3
                """,
                reason,
                risk_uuid,
                tenant_id,
            )

            row = await conn.fetchrow(
                """
                SELECT r.*, rc.display_name AS category_name
                FROM risks r
                LEFT JOIN risk_categories rc ON rc.id = r.category_id
                WHERE r.id = $1 AND r.tenant_id = $2
                """,
                risk_uuid,
                tenant_id,
            )
            return _row_to_dict(row)

    # ------------------------------------------------------------------
    # add_assessment
    # ------------------------------------------------------------------
    async def add_assessment(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        data: AssessmentCreate,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            # Resolve risk uuid from risk_id string or direct uuid
            risk_row = await conn.fetchrow(
                """
                SELECT id FROM risks
                WHERE tenant_id = $1 AND (id::text = $2 OR risk_id = $2)
                """,
                tenant_id,
                data.risk_id,
            )
            if not risk_row:
                raise LookupError(f"Risk not found: {data.risk_id}")

            risk_uuid = risk_row["id"]
            inherent_score = _scorer.score(data.inherent_likelihood, data.inherent_impact)
            residual_score: float | None = None
            if data.residual_likelihood and data.residual_impact:
                residual_score = _scorer.score(
                    data.residual_likelihood, data.residual_impact
                )

            assessment_id = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO risk_assessments (
                    id, tenant_id, risk_id,
                    assessed_by, inherent_likelihood, inherent_impact, inherent_score,
                    residual_likelihood, residual_impact, residual_score,
                    assessment_notes, controls_evaluated, assessed_at
                ) VALUES (
                    $1,$2,$3,
                    $4,$5,$6,$7,
                    $8,$9,$10,
                    $11,$12,NOW()
                )
                """,
                assessment_id,
                tenant_id,
                risk_uuid,
                data.assessed_by,
                data.inherent_likelihood,
                data.inherent_impact,
                inherent_score,
                data.residual_likelihood,
                data.residual_impact,
                residual_score,
                data.assessment_notes,
                data.controls_evaluated,
            )

            # Also insert score history (immutable)
            await conn.execute(
                """
                INSERT INTO risk_score_history (
                    id, tenant_id, risk_id,
                    inherent_likelihood, inherent_impact, inherent_score,
                    residual_likelihood, residual_impact, residual_score,
                    change_reason, changed_by, recorded_at
                ) VALUES (
                    $1,$2,$3,
                    $4,$5,$6,
                    $7,$8,$9,
                    'formal_assessment',$10,NOW()
                )
                """,
                str(uuid.uuid4()),
                tenant_id,
                risk_uuid,
                data.inherent_likelihood,
                data.inherent_impact,
                inherent_score,
                data.residual_likelihood,
                data.residual_impact,
                residual_score,
                data.assessed_by,
            )

            row = await conn.fetchrow(
                "SELECT * FROM risk_assessments WHERE id = $1", assessment_id
            )
            return _row_to_dict(row)

    # ------------------------------------------------------------------
    # get_register
    # ------------------------------------------------------------------
    async def get_register(self, pool: asyncpg.Pool, tenant_id: str) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            total_row = await conn.fetchrow(
                "SELECT COUNT(*) AS total FROM risks WHERE tenant_id = $1", tenant_id
            )

            status_rows = await conn.fetch(
                """
                SELECT status, COUNT(*) AS cnt
                FROM risks WHERE tenant_id = $1
                GROUP BY status
                """,
                tenant_id,
            )

            category_rows = await conn.fetch(
                """
                SELECT rc.display_name AS category, COUNT(*) AS cnt
                FROM risks r
                LEFT JOIN risk_categories rc ON rc.id = r.category_id
                WHERE r.tenant_id = $1
                GROUP BY rc.display_name
                """,
                tenant_id,
            )

            score_rows = await conn.fetch(
                """
                SELECT COALESCE(residual_score, inherent_score) AS score
                FROM risks WHERE tenant_id = $1 AND status != 'closed'
                """,
                tenant_id,
            )

            appetite_row = await conn.fetchrow(
                """
                SELECT COUNT(*) AS cnt
                FROM risks r
                JOIN risk_appetite ra
                  ON ra.tenant_id = r.tenant_id AND ra.category_id = r.category_id
                WHERE r.tenant_id = $1
                  AND r.status != 'closed'
                  AND COALESCE(r.residual_score, r.inherent_score) > ra.max_acceptable_score
                """,
                tenant_id,
            )

            overdue_row = await conn.fetchrow(
                """
                SELECT COUNT(*) AS cnt FROM risks
                WHERE tenant_id = $1
                  AND status = 'open'
                  AND review_date < CURRENT_DATE
                """,
                tenant_id,
            )

        score_dist = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for r in score_rows:
            s = r["score"] or 0
            if s >= 20:
                score_dist["critical"] += 1
            elif s >= 15:
                score_dist["high"] += 1
            elif s >= 9:
                score_dist["medium"] += 1
            else:
                score_dist["low"] += 1

        return {
            "total": total_row["total"] if total_row else 0,
            "by_status": {r["status"]: r["cnt"] for r in status_rows},
            "by_category": {r["category"] or "Uncategorised": r["cnt"] for r in category_rows},
            "score_distribution": score_dist,
            "above_appetite": appetite_row["cnt"] if appetite_row else 0,
            "overdue_review": overdue_row["cnt"] if overdue_row else 0,
        }

    # ------------------------------------------------------------------
    # get_heatmap_data
    # ------------------------------------------------------------------
    async def get_heatmap_data(self, pool: asyncpg.Pool, tenant_id: str) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT
                    r.risk_id, r.title,
                    r.inherent_likelihood, r.inherent_impact,
                    r.residual_likelihood, r.residual_impact,
                    rc.display_name AS category, r.owner, r.status
                FROM risks r
                LEFT JOIN risk_categories rc ON rc.id = r.category_id
                WHERE r.tenant_id = $1 AND r.status != 'closed'
                ORDER BY COALESCE(r.residual_score, r.inherent_score) DESC
                """,
                tenant_id,
            )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # auto_create_from_finding
    # ------------------------------------------------------------------
    async def auto_create_from_finding(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        finding_id: str,
        finding_data: dict,
    ) -> dict | None:
        # Check for existing risk with same auto_source_id
        async with tenant_conn(pool, tenant_id) as conn:
            existing = await conn.fetchrow(
                "SELECT id FROM risks WHERE tenant_id = $1 AND auto_source_id = $2",
                tenant_id,
                finding_id,
            )
        if existing:
            return None

        # Map severity to scores
        severity = (finding_data.get("severity") or "medium").lower()
        score_map = {
            "critical": (5, 5),
            "high": (4, 4),
            "medium": (3, 3),
            "low": (2, 2),
        }
        likelihood, impact = score_map.get(severity, (3, 3))

        # Map finding_type to category_key
        finding_type = (finding_data.get("finding_type") or "").lower()
        category_key = "operational"
        for prefix, cat in _FINDING_TYPE_TO_CATEGORY.items():
            if finding_type.startswith(prefix):
                category_key = cat
                break

        risk_id = f"RISK-AUTO-{finding_id[:8].upper()}"
        title = finding_data.get("title") or f"Auto-risk from finding {finding_id[:8]}"
        description = finding_data.get("description") or f"Automatically created from monitoring finding {finding_id}."

        # Verify the category_key exists; fall back gracefully
        async with tenant_conn(pool, tenant_id) as conn:
            cat_check = await conn.fetchrow(
                "SELECT id FROM risk_categories WHERE category_key = $1", category_key
            )
        if not cat_check:
            category_key = "operational"

        data = RiskCreate(
            risk_id=risk_id,
            title=title,
            description=description,
            category_key=category_key,
            inherent_likelihood=likelihood,
            inherent_impact=impact,
            source="monitoring_auto",
        )

        try:
            return await self.create(pool, tenant_id, data, auto_source_id=finding_id)
        except Exception as exc:
            logger.error("auto_create_from_finding failed: %s", exc)
            return None
