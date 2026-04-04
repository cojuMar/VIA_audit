from __future__ import annotations

import datetime

import asyncpg
from minio import Minio

from .db import tenant_conn
from .field_audit_manager import FieldAuditManager
from .models import FieldAuditCreate, ResponsePayload, SyncBatchPayload
from .template_manager import TemplateManager


class SyncEngine:
    def __init__(self, pool: asyncpg.Pool, minio_client: Minio) -> None:
        self.pool = pool
        self.minio_client = minio_client

    # ------------------------------------------------------------------

    async def process_sync_batch(
        self, tenant_id: str, data: SyncBatchPayload
    ) -> dict:
        """
        Process an offline sync batch from a mobile device.

        For each field_audit in data.field_audits:
          - Deduplicate by (device_id + client_created_at).
          - Insert the audit and its nested responses if not already present.
        For standalone responses in data.responses, insert with sync_id dedup.
        Record an immutable sync_session row.
        """
        audit_mgr = FieldAuditManager(self.pool)

        new_audits = 0
        duplicate_audits = 0
        responses_inserted = 0
        responses_skipped = 0
        errors: list[str] = []

        for audit_dict in data.field_audits:
            try:
                device_id = audit_dict.get("device_id") or data.device_id
                client_created_at = audit_dict.get("client_created_at")

                # Dedup check: look for an existing audit with same device+timestamp
                existing_id: str | None = None
                if device_id and client_created_at:
                    async with tenant_conn(self.pool, tenant_id) as conn:
                        existing_id = await conn.fetchval(
                            """
                            SELECT id FROM field_audits
                            WHERE device_id = $1
                              AND client_created_at = $2::timestamptz
                            LIMIT 1
                            """,
                            device_id,
                            client_created_at,
                        )

                if existing_id:
                    duplicate_audits += 1
                    audit_id = existing_id
                else:
                    # Build FieldAuditCreate from dict
                    create_data = FieldAuditCreate(
                        assignment_id=audit_dict.get("assignment_id"),
                        template_id=audit_dict["template_id"],
                        auditor_email=audit_dict.get(
                            "auditor_email", data.auditor_email
                        ),
                        auditor_name=audit_dict.get("auditor_name"),
                        location_name=audit_dict.get("location_name", ""),
                        device_id=device_id,
                        client_created_at=client_created_at,
                        gps_latitude=audit_dict.get("gps_latitude"),
                        gps_longitude=audit_dict.get("gps_longitude"),
                        gps_accuracy_meters=audit_dict.get("gps_accuracy_meters"),
                        notes=audit_dict.get("notes"),
                    )
                    created = await audit_mgr.create_audit(tenant_id, create_data)
                    audit_id = str(created["id"])
                    new_audits += 1

                # Insert nested responses
                nested_responses = audit_dict.get("responses", [])
                for resp_dict in nested_responses:
                    try:
                        resp = ResponsePayload(**resp_dict)
                        async with tenant_conn(self.pool, tenant_id) as conn:
                            row = await conn.fetchrow(
                                """
                                INSERT INTO field_audit_responses (
                                    field_audit_id, question_id, response_value,
                                    numeric_response, boolean_response,
                                    gps_latitude, gps_longitude, comment,
                                    is_finding, finding_severity, photo_references,
                                    client_answered_at, sync_id, created_at
                                )
                                SELECT
                                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                                    $12::timestamptz, $13, NOW()
                                WHERE NOT EXISTS (
                                    SELECT 1 FROM field_audit_responses
                                    WHERE sync_id = $13
                                )
                                RETURNING id
                                """,
                                audit_id,
                                resp.question_id,
                                resp.response_value,
                                resp.numeric_response,
                                resp.boolean_response,
                                resp.gps_latitude,
                                resp.gps_longitude,
                                resp.comment,
                                resp.is_finding,
                                resp.finding_severity,
                                resp.photo_references,
                                resp.client_answered_at,
                                resp.sync_id,
                            )
                        if row is not None:
                            responses_inserted += 1
                        else:
                            responses_skipped += 1
                    except Exception as exc:
                        errors.append(f"Response error: {exc}")

            except Exception as exc:
                errors.append(f"Audit error: {exc}")

        # Standalone responses (for audits that already exist on server)
        for resp in data.responses:
            try:
                async with tenant_conn(self.pool, tenant_id) as conn:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO field_audit_responses (
                            field_audit_id, question_id, response_value,
                            numeric_response, boolean_response,
                            gps_latitude, gps_longitude, comment,
                            is_finding, finding_severity, photo_references,
                            client_answered_at, sync_id, created_at
                        )
                        SELECT
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                            $12::timestamptz, $13, NOW()
                        WHERE NOT EXISTS (
                            SELECT 1 FROM field_audit_responses WHERE sync_id = $13
                        )
                        RETURNING id
                        """,
                        None,  # field_audit_id may be set from resp context
                        resp.question_id,
                        resp.response_value,
                        resp.numeric_response,
                        resp.boolean_response,
                        resp.gps_latitude,
                        resp.gps_longitude,
                        resp.comment,
                        resp.is_finding,
                        resp.finding_severity,
                        resp.photo_references,
                        resp.client_answered_at,
                        resp.sync_id,
                    )
                if row is not None:
                    responses_inserted += 1
                else:
                    responses_skipped += 1
            except Exception as exc:
                errors.append(f"Standalone response error: {exc}")

        # Determine sync status
        sync_status = "partial" if errors else "success"
        records_uploaded = new_audits + responses_inserted

        # Record immutable sync_session
        async with tenant_conn(self.pool, tenant_id) as conn:
            session_row = await conn.fetchrow(
                """
                INSERT INTO sync_sessions (
                    device_id,
                    auditor_email,
                    records_uploaded,
                    sync_status,
                    error_details,
                    synced_at
                ) VALUES ($1, $2, $3, $4, $5, NOW())
                RETURNING id
                """,
                data.device_id,
                data.auditor_email,
                records_uploaded,
                sync_status,
                "; ".join(errors) if errors else None,
            )
        sync_session_id = str(session_row["id"]) if session_row else None

        return {
            "new_audits": new_audits,
            "duplicate_audits": duplicate_audits,
            "responses_inserted": responses_inserted,
            "responses_skipped": responses_skipped,
            "sync_session_id": sync_session_id,
            "sync_status": sync_status,
            "errors": errors,
        }

    # ------------------------------------------------------------------

    async def get_assignments_for_device(
        self,
        tenant_id: str,
        email: str,
        last_sync: str | None = None,
    ) -> dict:
        """
        Build a data package for device download: active assignments for this
        auditor plus the full template+questions for each.
        """
        tmpl_mgr = TemplateManager(self.pool)

        conditions = ["a.assigned_to_email = $1", "a.status NOT IN ('completed', 'cancelled')"]
        params: list = [email]

        if last_sync:
            params.append(last_sync)
            conditions.append(f"a.updated_at > ${len(params)}::timestamptz")

        where_clause = "WHERE " + " AND ".join(conditions)

        query = f"""
            SELECT a.*, t.name AS template_name
            FROM field_audit_assignments a
            LEFT JOIN field_audit_templates t ON t.id = a.template_id
            {where_clause}
            ORDER BY a.scheduled_date
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            assignment_rows = await conn.fetch(query, *params)

        assignments = [dict(r) for r in assignment_rows]

        # Collect unique template IDs
        template_ids = list({str(a["template_id"]) for a in assignments})
        templates = []
        for tid in template_ids:
            tmpl = await tmpl_mgr.get_template_with_questions(tid)
            if tmpl:
                templates.append(tmpl)

        server_time = datetime.datetime.now(datetime.timezone.utc).isoformat()

        return {
            "assignments": assignments,
            "templates": templates,
            "server_time": server_time,
        }

    # ------------------------------------------------------------------

    async def get_sync_history(
        self,
        tenant_id: str,
        device_id: str | None = None,
        email: str | None = None,
    ) -> list[dict]:
        """Return up to 50 most-recent sync sessions, optionally filtered."""
        conditions: list[str] = []
        params: list = []

        if device_id is not None:
            params.append(device_id)
            conditions.append(f"device_id = ${len(params)}")

        if email is not None:
            params.append(email)
            conditions.append(f"auditor_email = ${len(params)}")

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        query = f"""
            SELECT *
            FROM sync_sessions
            {where_clause}
            ORDER BY synced_at DESC
            LIMIT 50
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]
