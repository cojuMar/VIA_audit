from __future__ import annotations

import uuid
from typing import Any

import asyncpg

from .config import settings
from .db import tenant_conn
from .models import PBCFulfillmentCreate, PBCListCreate, PBCRequestCreate


def _get_minio_client():
    from minio import Minio

    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=False,
    )


class PBCManager:

    # ------------------------------------------------------------------
    # Lists
    # ------------------------------------------------------------------

    async def create_list(
        self, pool: asyncpg.Pool, tenant_id: str, data: PBCListCreate
    ) -> dict:
        list_id = str(uuid.uuid4())
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO pbc_request_lists (
                    id, tenant_id, engagement_id, list_name,
                    description, due_date, status, created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, 'draft', NOW(), NOW())
                RETURNING *
                """,
                list_id,
                tenant_id,
                data.engagement_id,
                data.list_name,
                data.description,
                data.due_date,
            )
        return dict(row)

    async def update_list(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        list_id: str,
        updates: dict,
    ) -> dict:
        allowed = {"list_name", "description", "due_date", "status"}
        set_parts = []
        params: list[Any] = [list_id, tenant_id]
        idx = 3
        for key, val in updates.items():
            if key in allowed:
                set_parts.append(f"{key} = ${idx}")
                params.append(val)
                idx += 1
        if not set_parts:
            raise ValueError("No valid fields to update")
        set_parts.append("updated_at = NOW()")
        set_clause = ", ".join(set_parts)
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE pbc_request_lists SET {set_clause}
                WHERE id = $1 AND tenant_id = $2
                RETURNING *
                """,
                *params,
            )
        if row is None:
            raise ValueError(f"PBC list {list_id} not found")
        return dict(row)

    async def get_list_with_requests(
        self, pool: asyncpg.Pool, tenant_id: str, list_id: str
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            list_row = await conn.fetchrow(
                "SELECT * FROM pbc_request_lists WHERE id = $1 AND tenant_id = $2",
                list_id,
                tenant_id,
            )
            if list_row is None:
                raise ValueError(f"PBC list {list_id} not found")

            request_rows = await conn.fetch(
                """
                SELECT * FROM pbc_requests
                WHERE list_id = $1 AND tenant_id = $2
                ORDER BY request_number ASC
                """,
                list_id,
                tenant_id,
            )

            # Latest fulfillment per request
            fulfillment_rows = await conn.fetch(
                """
                SELECT DISTINCT ON (request_id)
                    request_id, submitted_by, response_text, file_name,
                    submitted_at, submission_notes
                FROM pbc_fulfillments
                WHERE request_id = ANY(
                    SELECT id FROM pbc_requests WHERE list_id = $1 AND tenant_id = $2
                ) AND tenant_id = $2
                ORDER BY request_id, submitted_at DESC
                """,
                list_id,
                tenant_id,
            )

        fulfillment_map = {str(r["request_id"]): dict(r) for r in fulfillment_rows}

        requests = []
        for req in request_rows:
            req_dict = dict(req)
            req_dict["latest_fulfillment"] = fulfillment_map.get(
                str(req["id"])
            )
            requests.append(req_dict)

        return {"list": dict(list_row), "requests": requests}

    async def get_list_status(
        self, pool: asyncpg.Pool, tenant_id: str, list_id: str
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*)::int                                                    AS total,
                    COUNT(*) FILTER (WHERE status = 'open')::int                    AS open,
                    COUNT(*) FILTER (WHERE status = 'in_progress')::int             AS in_progress,
                    COUNT(*) FILTER (WHERE status = 'fulfilled')::int               AS fulfilled,
                    COUNT(*) FILTER (WHERE status = 'not_applicable')::int          AS not_applicable,
                    COUNT(*) FILTER (
                        WHERE due_date < CURRENT_DATE
                          AND status IN ('open', 'in_progress')
                    )::int                                                           AS overdue
                FROM pbc_requests
                WHERE list_id = $1 AND tenant_id = $2
                """,
                list_id,
                tenant_id,
            )
        total = row["total"] or 0
        fulfilled = row["fulfilled"] or 0
        not_applicable = row["not_applicable"] or 0
        completed = fulfilled + not_applicable
        return {
            "total": total,
            "open": row["open"] or 0,
            "in_progress": row["in_progress"] or 0,
            "fulfilled": fulfilled,
            "not_applicable": not_applicable,
            "overdue": row["overdue"] or 0,
            "completion_pct": round(completed / total * 100, 1) if total else 0.0,
        }

    # ------------------------------------------------------------------
    # Requests
    # ------------------------------------------------------------------

    async def add_request(
        self, pool: asyncpg.Pool, tenant_id: str, data: PBCRequestCreate
    ) -> dict:
        request_id = str(uuid.uuid4())
        async with tenant_conn(pool, tenant_id) as conn:
            num_row = await conn.fetchrow(
                """
                SELECT COALESCE(MAX(request_number), 0) + 1 AS next_num
                FROM pbc_requests
                WHERE list_id = $1 AND tenant_id = $2
                """,
                data.list_id,
                tenant_id,
            )
            next_num = num_row["next_num"]
            row = await conn.fetchrow(
                """
                INSERT INTO pbc_requests (
                    id, tenant_id, list_id, request_number,
                    title, description, category, priority,
                    assigned_to, due_date, framework_control_ref,
                    status, created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                        'open', NOW(), NOW())
                RETURNING *
                """,
                request_id,
                tenant_id,
                data.list_id,
                next_num,
                data.title,
                data.description,
                data.category,
                data.priority,
                data.assigned_to,
                data.due_date,
                data.framework_control_ref,
            )
        return dict(row)

    async def bulk_add_requests(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        list_id: str,
        requests: list[PBCRequestCreate],
    ) -> dict:
        if not requests:
            return {"added": 0}

        async with tenant_conn(pool, tenant_id) as conn:
            num_row = await conn.fetchrow(
                """
                SELECT COALESCE(MAX(request_number), 0) AS max_num
                FROM pbc_requests
                WHERE list_id = $1 AND tenant_id = $2
                """,
                list_id,
                tenant_id,
            )
            base_num = num_row["max_num"]

            for i, req in enumerate(requests, start=1):
                request_id = str(uuid.uuid4())
                await conn.execute(
                    """
                    INSERT INTO pbc_requests (
                        id, tenant_id, list_id, request_number,
                        title, description, category, priority,
                        assigned_to, due_date, framework_control_ref,
                        status, created_at, updated_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                            'open', NOW(), NOW())
                    """,
                    request_id,
                    tenant_id,
                    list_id,
                    base_num + i,
                    req.title,
                    req.description,
                    req.category,
                    req.priority,
                    req.assigned_to,
                    req.due_date,
                    req.framework_control_ref,
                )
        return {"added": len(requests)}

    # ------------------------------------------------------------------
    # Fulfillment (immutable)
    # ------------------------------------------------------------------

    async def fulfill_request(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        request_id: str,
        data: PBCFulfillmentCreate,
        file_bytes: bytes | None,
        file_name: str | None,
    ) -> dict:
        fulfillment_id = str(uuid.uuid4())
        file_key: str | None = None

        # Upload to MinIO if file provided
        if file_bytes and file_name:
            try:
                import io

                client = _get_minio_client()
                object_key = (
                    f"pbc/{tenant_id}/{request_id}/{uuid.uuid4()}_{file_name}"
                )
                client.put_object(
                    settings.minio_bucket_workpapers,
                    object_key,
                    io.BytesIO(file_bytes),
                    length=len(file_bytes),
                )
                file_key = object_key
            except Exception:
                # Graceful fallback — continue without file
                file_key = None

        async with tenant_conn(pool, tenant_id) as conn:
            # Fetch list_id for the fulfillment record
            req_row = await conn.fetchrow(
                "SELECT list_id FROM pbc_requests WHERE id = $1 AND tenant_id = $2",
                request_id,
                tenant_id,
            )
            if req_row is None:
                raise ValueError(f"Request {request_id} not found")
            list_id = req_row["list_id"]

            # INSERT fulfillment (immutable)
            ful_row = await conn.fetchrow(
                """
                INSERT INTO pbc_fulfillments (
                    id, tenant_id, request_id,
                    submitted_by, response_text, file_name, minio_key,
                    submission_notes, submitted_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                RETURNING *
                """,
                fulfillment_id,
                tenant_id,
                request_id,
                data.submitted_by,
                data.response_text,
                file_name,
                file_key,
                data.submission_notes,
            )

            # UPDATE request status to fulfilled
            req_updated = await conn.fetchrow(
                """
                UPDATE pbc_requests
                SET status = 'fulfilled', updated_at = NOW()
                WHERE id = $1 AND tenant_id = $2
                RETURNING *
                """,
                request_id,
                tenant_id,
            )

        return {"fulfillment": dict(ful_row), "request": dict(req_updated)}

    # ------------------------------------------------------------------
    # Overdue
    # ------------------------------------------------------------------

    async def get_overdue_requests(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        engagement_id: str | None = None,
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            if engagement_id:
                rows = await conn.fetch(
                    """
                    SELECT r.*
                    FROM pbc_requests r
                    JOIN pbc_request_lists l ON l.id = r.list_id
                    WHERE r.tenant_id = $1
                      AND r.due_date < CURRENT_DATE
                      AND r.status IN ('open', 'in_progress')
                      AND l.engagement_id = $2
                    ORDER BY r.due_date ASC
                    """,
                    tenant_id,
                    engagement_id,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM pbc_requests
                    WHERE tenant_id = $1
                      AND due_date < CURRENT_DATE
                      AND status IN ('open', 'in_progress')
                    ORDER BY due_date ASC
                    """,
                    tenant_id,
                )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Not applicable
    # ------------------------------------------------------------------

    async def mark_not_applicable(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        request_id: str,
        reason: str,
    ) -> dict:
        fulfillment_id = str(uuid.uuid4())
        async with tenant_conn(pool, tenant_id) as conn:
            req_row = await conn.fetchrow(
                "SELECT list_id FROM pbc_requests WHERE id = $1 AND tenant_id = $2",
                request_id,
                tenant_id,
            )
            if req_row is None:
                raise ValueError(f"Request {request_id} not found")
            list_id = req_row["list_id"]

            # Insert an immutable fulfillment record for audit trail
            await conn.execute(
                """
                INSERT INTO pbc_fulfillments (
                    id, tenant_id, request_id,
                    submitted_by, response_text, submission_notes, submitted_at
                )
                VALUES ($1, $2, $3, 'system', 'N/A', $4, NOW())
                """,
                fulfillment_id,
                tenant_id,
                request_id,
                reason,
            )

            row = await conn.fetchrow(
                """
                UPDATE pbc_requests
                SET status = 'not_applicable', updated_at = NOW()
                WHERE id = $1 AND tenant_id = $2
                RETURNING *
                """,
                request_id,
                tenant_id,
            )
        return dict(row)

    # ------------------------------------------------------------------
    # Fulfillment history
    # ------------------------------------------------------------------

    async def get_fulfillment_history(
        self, pool: asyncpg.Pool, tenant_id: str, request_id: str
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM pbc_fulfillments
                WHERE request_id = $1 AND tenant_id = $2
                ORDER BY submitted_at ASC
                """,
                request_id,
                tenant_id,
            )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # List all PBC lists for a tenant / engagement
    # ------------------------------------------------------------------

    async def list_pbc_lists(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        engagement_id: str | None = None,
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            if engagement_id:
                rows = await conn.fetch(
                    """
                    SELECT * FROM pbc_request_lists
                    WHERE tenant_id = $1 AND engagement_id = $2
                    ORDER BY created_at DESC
                    """,
                    tenant_id,
                    engagement_id,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM pbc_request_lists
                    WHERE tenant_id = $1
                    ORDER BY created_at DESC
                    """,
                    tenant_id,
                )
        return [dict(r) for r in rows]
