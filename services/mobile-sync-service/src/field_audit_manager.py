from __future__ import annotations

import asyncpg

from .db import tenant_conn
from .models import FieldAuditCreate, ResponsePayload


class FieldAuditManager:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # ------------------------------------------------------------------

    async def create_audit(
        self, tenant_id: str, data: FieldAuditCreate
    ) -> dict:
        """Insert a new field audit record and optionally update assignment status."""
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO field_audits (
                    assignment_id,
                    template_id,
                    auditor_email,
                    auditor_name,
                    location_name,
                    device_id,
                    client_created_at,
                    gps_latitude,
                    gps_longitude,
                    gps_accuracy_meters,
                    notes,
                    status,
                    created_at,
                    updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6,
                    $7::timestamptz,
                    $8, $9, $10, $11,
                    'in_progress', NOW(), NOW()
                )
                RETURNING *
                """,
                data.assignment_id,
                data.template_id,
                data.auditor_email,
                data.auditor_name,
                data.location_name,
                data.device_id,
                data.client_created_at,
                data.gps_latitude,
                data.gps_longitude,
                data.gps_accuracy_meters,
                data.notes,
            )
            if data.assignment_id:
                await conn.execute(
                    """
                    UPDATE field_audit_assignments
                    SET status = 'in_progress', updated_at = NOW()
                    WHERE id = $1
                    """,
                    data.assignment_id,
                )
        return dict(row)

    # ------------------------------------------------------------------

    async def submit_audit(
        self,
        tenant_id: str,
        audit_id: str,
        auditor_signature: str | None = None,
    ) -> dict:
        """
        Mark audit as submitted.
        Computes overall_score (weighted yes_no compliance), risk_level, and
        total_findings count.
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            # Gather yes_no responses with weights
            response_rows = await conn.fetch(
                """
                SELECT
                    r.boolean_response,
                    r.is_finding,
                    COALESCE(q.weight, 1.0) AS weight,
                    q.question_type
                FROM field_audit_responses r
                LEFT JOIN field_audit_template_questions q
                       ON q.id = r.question_id
                WHERE r.field_audit_id = $1
                """,
                audit_id,
            )

            total_weight: float = 0.0
            compliant_weight: float = 0.0
            total_findings: int = 0

            for r in response_rows:
                if r["is_finding"]:
                    total_findings += 1
                if r["question_type"] == "yes_no" and r["boolean_response"] is not None:
                    w = float(r["weight"])
                    total_weight += w
                    if r["boolean_response"]:
                        compliant_weight += w

            overall_score: float | None = None
            risk_level = "low"
            if total_weight > 0:
                overall_score = round((compliant_weight / total_weight) * 100, 2)
                if overall_score < 50:
                    risk_level = "critical"
                elif overall_score < 70:
                    risk_level = "high"
                elif overall_score < 85:
                    risk_level = "medium"
                else:
                    risk_level = "low"

            row = await conn.fetchrow(
                """
                UPDATE field_audits
                SET
                    status            = 'submitted',
                    submitted_at      = NOW(),
                    auditor_signature = $1,
                    overall_score     = $2,
                    risk_level        = $3,
                    total_findings    = $4,
                    updated_at        = NOW()
                WHERE id = $5
                RETURNING *
                """,
                auditor_signature,
                overall_score,
                risk_level,
                total_findings,
                audit_id,
            )
        if row is None:
            raise ValueError(f"Audit {audit_id} not found")
        return dict(row)

    # ------------------------------------------------------------------

    async def get_audit(self, tenant_id: str, audit_id: str) -> dict | None:
        """Return an audit with its responses and photos joined."""
        async with tenant_conn(self.pool, tenant_id) as conn:
            audit_row = await conn.fetchrow(
                "SELECT * FROM field_audits WHERE id = $1", audit_id
            )
            if audit_row is None:
                return None

            response_rows = await conn.fetch(
                "SELECT * FROM field_audit_responses WHERE field_audit_id = $1 ORDER BY created_at",
                audit_id,
            )
            photo_rows = await conn.fetch(
                "SELECT * FROM field_audit_photos WHERE field_audit_id = $1 ORDER BY taken_at NULLS LAST",
                audit_id,
            )

        result = dict(audit_row)
        result["responses"] = [dict(r) for r in response_rows]
        result["photos"] = [dict(p) for p in photo_rows]
        return result

    # ------------------------------------------------------------------

    async def list_audits(
        self,
        tenant_id: str,
        email: str | None = None,
        status: str | None = None,
        assignment_id: str | None = None,
    ) -> list[dict]:
        """Return audits with optional filters and a response_count."""
        conditions: list[str] = []
        params: list = []

        if email is not None:
            params.append(email)
            conditions.append(f"a.auditor_email = ${len(params)}")

        if status is not None:
            params.append(status)
            conditions.append(f"a.status = ${len(params)}")

        if assignment_id is not None:
            params.append(assignment_id)
            conditions.append(f"a.assignment_id = ${len(params)}")

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        query = f"""
            SELECT
                a.*,
                (
                    SELECT COUNT(*) FROM field_audit_responses r
                    WHERE r.field_audit_id = a.id
                ) AS response_count
            FROM field_audits a
            {where_clause}
            ORDER BY a.created_at DESC
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------

    async def add_response(
        self,
        tenant_id: str,
        audit_id: str,
        data: ResponsePayload,
    ) -> dict:
        """
        Insert a single response (immutable table).
        Uses sync_id to prevent duplicates on re-sync.
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO field_audit_responses (
                    field_audit_id,
                    question_id,
                    response_value,
                    numeric_response,
                    boolean_response,
                    gps_latitude,
                    gps_longitude,
                    comment,
                    is_finding,
                    finding_severity,
                    photo_references,
                    client_answered_at,
                    sync_id,
                    created_at
                )
                SELECT
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                    $12::timestamptz, $13, NOW()
                WHERE NOT EXISTS (
                    SELECT 1 FROM field_audit_responses WHERE sync_id = $13
                )
                RETURNING *
                """,
                audit_id,
                data.question_id,
                data.response_value,
                data.numeric_response,
                data.boolean_response,
                data.gps_latitude,
                data.gps_longitude,
                data.comment,
                data.is_finding,
                data.finding_severity,
                data.photo_references,
                data.client_answered_at,
                data.sync_id,
            )
        if row is None:
            # Duplicate — return existing row
            async with tenant_conn(self.pool, tenant_id) as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM field_audit_responses WHERE sync_id = $1",
                    data.sync_id,
                )
        return dict(row)

    # ------------------------------------------------------------------

    async def add_responses_batch(
        self,
        tenant_id: str,
        audit_id: str,
        responses: list[ResponsePayload],
    ) -> dict:
        """Process a list of responses, deduplicating by sync_id."""
        inserted = 0
        skipped = 0

        for resp in responses:
            async with tenant_conn(self.pool, tenant_id) as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO field_audit_responses (
                        field_audit_id,
                        question_id,
                        response_value,
                        numeric_response,
                        boolean_response,
                        gps_latitude,
                        gps_longitude,
                        comment,
                        is_finding,
                        finding_severity,
                        photo_references,
                        client_answered_at,
                        sync_id,
                        created_at
                    )
                    SELECT
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                        $12::timestamptz, $13, NOW()
                    WHERE NOT EXISTS (
                        SELECT 1 FROM field_audit_responses WHERE sync_id = $13
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
                inserted += 1
            else:
                skipped += 1

        return {"inserted": inserted, "skipped": skipped}

    # ------------------------------------------------------------------

    async def get_audit_summary(
        self, tenant_id: str, audit_id: str
    ) -> dict:
        """
        Return a rich summary of the audit including findings breakdown,
        section scores, and photos.
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            audit_row = await conn.fetchrow(
                "SELECT * FROM field_audits WHERE id = $1", audit_id
            )
            if audit_row is None:
                raise ValueError(f"Audit {audit_id} not found")

            response_count: int = await conn.fetchval(
                "SELECT COUNT(*) FROM field_audit_responses WHERE field_audit_id = $1",
                audit_id,
            )

            finding_count: int = await conn.fetchval(
                """
                SELECT COUNT(*) FROM field_audit_responses
                WHERE field_audit_id = $1 AND is_finding = TRUE
                """,
                audit_id,
            )

            severity_rows = await conn.fetch(
                """
                SELECT finding_severity, COUNT(*) AS cnt
                FROM field_audit_responses
                WHERE field_audit_id = $1 AND is_finding = TRUE
                GROUP BY finding_severity
                """,
                audit_id,
            )

            section_rows = await conn.fetch(
                """
                SELECT
                    COALESCE(q.section_name, 'General') AS section_name,
                    COUNT(*) FILTER (
                        WHERE q.question_type = 'yes_no'
                        AND r.boolean_response IS NOT NULL
                    ) AS total_yn,
                    COUNT(*) FILTER (
                        WHERE q.question_type = 'yes_no'
                        AND r.boolean_response = TRUE
                    ) AS compliant_yn,
                    COUNT(*) FILTER (WHERE r.is_finding = TRUE) AS finding_count
                FROM field_audit_responses r
                LEFT JOIN field_audit_template_questions q
                       ON q.id = r.question_id
                WHERE r.field_audit_id = $1
                GROUP BY COALESCE(q.section_name, 'General')
                ORDER BY section_name
                """,
                audit_id,
            )

            photo_rows = await conn.fetch(
                """
                SELECT id, minio_object_key, caption, taken_at
                FROM field_audit_photos
                WHERE field_audit_id = $1
                ORDER BY taken_at NULLS LAST
                """,
                audit_id,
            )

        findings_by_severity: dict[str, int] = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
        }
        for sv in severity_rows:
            key = (sv["finding_severity"] or "low").lower()
            if key in findings_by_severity:
                findings_by_severity[key] = sv["cnt"]

        section_scores = []
        for sr in section_rows:
            total_yn = sr["total_yn"] or 0
            compliant_yn = sr["compliant_yn"] or 0
            score_pct = round((compliant_yn / total_yn) * 100, 2) if total_yn else None
            section_scores.append(
                {
                    "section_name": sr["section_name"],
                    "score_pct": score_pct,
                    "finding_count": sr["finding_count"],
                }
            )

        return {
            "audit": dict(audit_row),
            "response_count": response_count,
            "finding_count": finding_count,
            "findings_by_severity": findings_by_severity,
            "section_scores": section_scores,
            "photos": [dict(p) for p in photo_rows],
        }
