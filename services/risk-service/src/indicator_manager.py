import logging
import uuid
from datetime import datetime

import asyncpg

from .db import tenant_conn
from .models import IndicatorCreate, IndicatorReading

logger = logging.getLogger(__name__)


def _row_to_dict(row: asyncpg.Record) -> dict:
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


def _compute_status(
    value: float,
    threshold_green: float | None,
    threshold_amber: float | None,
) -> str:
    """
    value <= threshold_green → 'green'
    value <= threshold_amber → 'amber'
    else                     → 'red'
    """
    if threshold_green is not None and value <= threshold_green:
        return "green"
    if threshold_amber is not None and value <= threshold_amber:
        return "amber"
    return "red"


class IndicatorManager:
    # ------------------------------------------------------------------
    # create
    # ------------------------------------------------------------------
    async def create(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        data: IndicatorCreate,
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

            indicator_id = str(uuid.uuid4())
            row = await conn.fetchrow(
                """
                INSERT INTO risk_indicators (
                    id, tenant_id, risk_id,
                    indicator_name, description, metric_type,
                    threshold_green, threshold_amber, threshold_red,
                    data_source, current_status, created_at, updated_at
                ) VALUES (
                    $1,$2,$3,
                    $4,$5,$6,
                    $7,$8,$9,
                    $10,'unknown',NOW(),NOW()
                )
                RETURNING *
                """,
                indicator_id,
                tenant_id,
                risk_uuid,
                data.indicator_name,
                data.description,
                data.metric_type,
                data.threshold_green,
                data.threshold_amber,
                data.threshold_red,
                data.data_source,
            )
        return _row_to_dict(row)

    # ------------------------------------------------------------------
    # record_reading  (immutable insert)
    # ------------------------------------------------------------------
    async def record_reading(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        data: IndicatorReading,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            # 1. Look up indicator + thresholds
            indicator = await conn.fetchrow(
                """
                SELECT id, threshold_green, threshold_amber, threshold_red
                FROM risk_indicators
                WHERE id = $1 AND tenant_id = $2
                """,
                data.indicator_id,
                tenant_id,
            )
            if not indicator:
                raise LookupError(f"Indicator not found: {data.indicator_id}")

            # 2. Compute status
            status = _compute_status(
                data.value,
                indicator["threshold_green"],
                indicator["threshold_amber"],
            )

            # 3. INSERT risk_indicator_readings (immutable)
            reading_id = str(uuid.uuid4())
            row = await conn.fetchrow(
                """
                INSERT INTO risk_indicator_readings (
                    id, tenant_id, indicator_id,
                    value, status, notes, recorded_at
                ) VALUES (
                    $1,$2,$3,
                    $4,$5,$6,NOW()
                )
                RETURNING *
                """,
                reading_id,
                tenant_id,
                data.indicator_id,
                data.value,
                status,
                data.notes,
            )

            # 4. UPDATE risk_indicators: current_value, current_status, last_updated_at
            await conn.execute(
                """
                UPDATE risk_indicators
                SET current_value = $1,
                    current_status = $2,
                    last_updated_at = NOW(),
                    updated_at = NOW()
                WHERE id = $3 AND tenant_id = $4
                """,
                data.value,
                status,
                data.indicator_id,
                tenant_id,
            )

        result = _row_to_dict(row)
        result["computed_status"] = status
        return result

    # ------------------------------------------------------------------
    # get_for_risk  (with latest reading)
    # ------------------------------------------------------------------
    async def get_for_risk(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        risk_uuid: str,
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT
                    ri.*,
                    (SELECT value FROM risk_indicator_readings rir
                     WHERE rir.indicator_id = ri.id
                     ORDER BY rir.recorded_at DESC LIMIT 1) AS latest_value,
                    (SELECT status FROM risk_indicator_readings rir
                     WHERE rir.indicator_id = ri.id
                     ORDER BY rir.recorded_at DESC LIMIT 1) AS latest_status,
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
        return [_row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # list (with optional filters)
    # ------------------------------------------------------------------
    async def list(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        risk_id: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        conditions = ["ri.tenant_id = $1"]
        params: list = [tenant_id]
        idx = 2

        if risk_id:
            conditions.append(
                f"(ri.risk_id::text = ${idx} OR r.risk_id = ${idx})"
            )
            params.append(risk_id)
            idx += 1
        if status:
            conditions.append(f"ri.current_status = ${idx}")
            params.append(status)
            idx += 1

        where = " AND ".join(conditions)
        query = f"""
            SELECT ri.*, r.risk_id AS risk_code
            FROM risk_indicators ri
            LEFT JOIN risks r ON r.id = ri.risk_id
            WHERE {where}
            ORDER BY ri.created_at DESC
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [_row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # get_red_indicators
    # ------------------------------------------------------------------
    async def get_red_indicators(
        self, pool: asyncpg.Pool, tenant_id: str
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT ri.*, r.risk_id AS risk_code, r.title AS risk_title
                FROM risk_indicators ri
                LEFT JOIN risks r ON r.id = ri.risk_id
                WHERE ri.tenant_id = $1 AND ri.current_status = 'red'
                ORDER BY ri.last_updated_at DESC NULLS LAST
                """,
                tenant_id,
            )
        return [_row_to_dict(r) for r in rows]
