import logging
import uuid
from datetime import date, datetime

import asyncpg

from .db import tenant_conn
from .models import TreatmentCreate, TreatmentUpdate

logger = logging.getLogger(__name__)


def _row_to_dict(row: asyncpg.Record) -> dict:
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
        elif isinstance(v, date):
            d[k] = v.isoformat()
    return d


class TreatmentManager:
    # ------------------------------------------------------------------
    # create
    # ------------------------------------------------------------------
    async def create(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        data: TreatmentCreate,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            # Resolve risk
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

            treatment_id = str(uuid.uuid4())
            row = await conn.fetchrow(
                """
                INSERT INTO risk_treatments (
                    id, tenant_id, risk_id,
                    treatment_type, title, description,
                    owner, target_date, cost_estimate,
                    status, created_at, updated_at
                ) VALUES (
                    $1,$2,$3,
                    $4,$5,$6,
                    $7,$8,$9,
                    'planned',NOW(),NOW()
                )
                RETURNING *
                """,
                treatment_id,
                tenant_id,
                risk_uuid,
                data.treatment_type,
                data.title,
                data.description,
                data.owner,
                data.target_date,
                data.cost_estimate,
            )
        return _row_to_dict(row)

    # ------------------------------------------------------------------
    # update
    # ------------------------------------------------------------------
    async def update(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        treatment_id: str,
        data: TreatmentUpdate,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            existing = await conn.fetchrow(
                "SELECT id FROM risk_treatments WHERE id = $1 AND tenant_id = $2",
                treatment_id,
                tenant_id,
            )
            if not existing:
                raise LookupError(f"Treatment not found: {treatment_id}")

            sets: list[str] = []
            params: list = []
            idx = 1

            field_map = {
                "status": data.status,
                "completed_date": data.completed_date,
                "effectiveness_rating": data.effectiveness_rating,
                "description": data.description,
            }
            for col, val in field_map.items():
                if val is not None:
                    sets.append(f"{col} = ${idx}")
                    params.append(val)
                    idx += 1

            if sets:
                sets.append(f"updated_at = NOW()")
                params += [tenant_id, treatment_id]
                await conn.execute(
                    f"UPDATE risk_treatments SET {', '.join(sets)} "
                    f"WHERE tenant_id = ${idx} AND id = ${idx + 1}",
                    *params,
                )

            row = await conn.fetchrow(
                "SELECT * FROM risk_treatments WHERE id = $1", treatment_id
            )
        return _row_to_dict(row)

    # ------------------------------------------------------------------
    # list_for_risk
    # ------------------------------------------------------------------
    async def list_for_risk(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        risk_uuid: str,
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM risk_treatments
                WHERE risk_id = $1 AND tenant_id = $2
                ORDER BY created_at DESC
                """,
                risk_uuid,
                tenant_id,
            )
        return [_row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # list (all treatments, with optional filters)
    # ------------------------------------------------------------------
    async def list(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        status: str | None = None,
        risk_id: str | None = None,
    ) -> list[dict]:
        conditions = ["t.tenant_id = $1"]
        params: list = [tenant_id]
        idx = 2

        if status:
            conditions.append(f"t.status = ${idx}")
            params.append(status)
            idx += 1
        if risk_id:
            conditions.append(f"(t.risk_id::text = ${idx} OR r.risk_id = ${idx})")
            params.append(risk_id)
            idx += 1

        where = " AND ".join(conditions)
        query = f"""
            SELECT t.*, r.risk_id AS risk_code
            FROM risk_treatments t
            LEFT JOIN risks r ON r.id = t.risk_id
            WHERE {where}
            ORDER BY t.created_at DESC
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [_row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # get_effectiveness_summary
    # ------------------------------------------------------------------
    async def get_effectiveness_summary(
        self, pool: asyncpg.Pool, tenant_id: str
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            total_row = await conn.fetchrow(
                "SELECT COUNT(*) AS total FROM risk_treatments WHERE tenant_id = $1",
                tenant_id,
            )
            type_rows = await conn.fetch(
                """
                SELECT treatment_type, COUNT(*) AS cnt
                FROM risk_treatments WHERE tenant_id = $1
                GROUP BY treatment_type
                """,
                tenant_id,
            )
            status_rows = await conn.fetch(
                """
                SELECT status, COUNT(*) AS cnt
                FROM risk_treatments WHERE tenant_id = $1
                GROUP BY status
                """,
                tenant_id,
            )
            completed_row = await conn.fetchrow(
                """
                SELECT COUNT(*) AS cnt, AVG(effectiveness_rating) AS avg_eff
                FROM risk_treatments
                WHERE tenant_id = $1 AND status = 'completed'
                """,
                tenant_id,
            )
            overdue_row = await conn.fetchrow(
                """
                SELECT COUNT(*) AS cnt FROM risk_treatments
                WHERE tenant_id = $1
                  AND status NOT IN ('completed', 'cancelled')
                  AND target_date < CURRENT_DATE
                """,
                tenant_id,
            )

        avg_eff = None
        if completed_row and completed_row["avg_eff"] is not None:
            avg_eff = round(float(completed_row["avg_eff"]), 2)

        return {
            "total": total_row["total"] if total_row else 0,
            "by_type": {r["treatment_type"]: r["cnt"] for r in type_rows},
            "by_status": {r["status"]: r["cnt"] for r in status_rows},
            "completed_count": completed_row["cnt"] if completed_row else 0,
            "avg_effectiveness": avg_eff,
            "overdue_count": overdue_row["cnt"] if overdue_row else 0,
        }
