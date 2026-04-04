from __future__ import annotations

import hashlib
from datetime import date, timedelta

import asyncpg

from .db import tenant_conn
from .models import AcknowledgmentRecord, PolicyCreate


def _next_version(current: str) -> str:
    """Increment the minor part of a 'X.Y' version string."""
    try:
        major, minor = current.split(".")
        return f"{major}.{int(minor) + 1}"
    except (ValueError, AttributeError):
        return "1.1"


def _content_hash(title: str, version: str, change_summary: str) -> str:
    payload = f"{title}|{version}|{change_summary}"
    return hashlib.sha256(payload.encode()).hexdigest()


class PolicyManager:

    @staticmethod
    def _to_dict(record: asyncpg.Record) -> dict:
        return dict(record)

    # ------------------------------------------------------------------
    async def create_policy(
        self, pool: asyncpg.Pool, tenant_id: str, data: PolicyCreate
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            async with conn.transaction():
                policy_row = await conn.fetchrow(
                    """
                    INSERT INTO policies (
                        tenant_id, policy_key, title, description, category,
                        applies_to_roles, applies_to_departments,
                        acknowledgment_required, acknowledgment_frequency_days,
                        current_version
                    )
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'1.0')
                    RETURNING *
                    """,
                    tenant_id,
                    data.policy_key,
                    data.title,
                    data.description,
                    data.category,
                    data.applies_to_roles,
                    data.applies_to_departments,
                    data.acknowledgment_required,
                    data.acknowledgment_frequency_days,
                )
                version = "1.0"
                content_hash = _content_hash(data.title, version, "Initial version")
                await conn.execute(
                    """
                    INSERT INTO policy_versions (
                        tenant_id, policy_id, version_number,
                        change_summary, content_hash, created_by
                    )
                    VALUES ($1,$2,$3,$4,$5,$6)
                    """,
                    tenant_id,
                    policy_row["id"],
                    version,
                    "Initial version",
                    content_hash,
                    "system",
                )
                return self._to_dict(policy_row)

    async def update_policy(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        policy_id: str,
        updates: dict,
        change_summary: str,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            async with conn.transaction():
                current = await conn.fetchrow(
                    "SELECT * FROM policies WHERE tenant_id=$1 AND id=$2",
                    tenant_id,
                    policy_id,
                )
                if current is None:
                    raise ValueError(f"Policy {policy_id} not found")

                new_version = _next_version(current["current_version"])

                # Build a dynamic SET clause from the provided updates dict
                allowed = {
                    "title", "description", "category", "applies_to_roles",
                    "applies_to_departments", "acknowledgment_required",
                    "acknowledgment_frequency_days",
                }
                set_parts = []
                params: list = [tenant_id, policy_id]
                idx = 3
                for key, value in updates.items():
                    if key in allowed:
                        set_parts.append(f"{key}=${idx}")
                        params.append(value)
                        idx += 1
                set_parts.append(f"current_version=${idx}")
                params.append(new_version)
                idx += 1
                set_parts.append("updated_at=NOW()")

                policy_row = await conn.fetchrow(
                    f"UPDATE policies SET {', '.join(set_parts)} "
                    f"WHERE tenant_id=$1 AND id=$2 RETURNING *",
                    *params,
                )

                title = updates.get("title", current["title"])
                content_hash = _content_hash(title, new_version, change_summary)
                await conn.execute(
                    """
                    INSERT INTO policy_versions (
                        tenant_id, policy_id, version_number,
                        change_summary, content_hash, created_by
                    )
                    VALUES ($1,$2,$3,$4,$5,$6)
                    """,
                    tenant_id,
                    policy_id,
                    new_version,
                    change_summary,
                    content_hash,
                    "system",
                )
                return self._to_dict(policy_row)

    async def list_policies(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        category: str | None = None,
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            if category:
                rows = await conn.fetch(
                    "SELECT * FROM policies WHERE tenant_id=$1 AND category=$2 "
                    "AND is_active=TRUE ORDER BY title",
                    tenant_id,
                    category,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM policies WHERE tenant_id=$1 AND is_active=TRUE ORDER BY title",
                    tenant_id,
                )
            return [self._to_dict(r) for r in rows]

    async def record_acknowledgment(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        data: AcknowledgmentRecord,
        ip: str,
        user_agent: str,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO policy_acknowledgments (
                    tenant_id, policy_id, employee_id, policy_version,
                    acknowledgment_method, ip_address, user_agent
                )
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                RETURNING *
                """,
                tenant_id,
                data.policy_id,
                data.employee_id,
                data.policy_version,
                data.acknowledgment_method,
                ip,
                user_agent,
            )
            return self._to_dict(row)

    async def get_employee_ack_status(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        employee_id: str,
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            # Fetch employee to know their role/department
            emp = await conn.fetchrow(
                "SELECT job_role, department FROM employees "
                "WHERE tenant_id=$1 AND employee_id=$2",
                tenant_id,
                employee_id,
            )
            if emp is None:
                return []

            emp_role = emp["job_role"]
            emp_dept = emp["department"]

            # Policies that apply to this employee
            policies = await conn.fetch(
                """
                SELECT * FROM policies
                WHERE tenant_id=$1
                  AND is_active=TRUE
                  AND acknowledgment_required=TRUE
                  AND (
                      'all' = ANY(applies_to_roles)
                      OR $2 = ANY(applies_to_roles)
                  )
                """,
                tenant_id,
                emp_role,
            )

            result = []
            today = date.today()
            for policy in policies:
                # Most recent acknowledgment for this employee+policy
                ack = await conn.fetchrow(
                    """
                    SELECT acknowledged_at
                    FROM policy_acknowledgments
                    WHERE tenant_id=$1 AND policy_id=$2 AND employee_id=$3
                    ORDER BY acknowledged_at DESC
                    LIMIT 1
                    """,
                    tenant_id,
                    str(policy["id"]),
                    employee_id,
                )

                freq = policy["acknowledgment_frequency_days"]
                acknowledged = ack is not None
                acknowledged_at = ack["acknowledged_at"] if ack else None
                is_overdue = True
                days_until_due = None

                if acknowledged_at:
                    due_date = acknowledged_at.date() + timedelta(days=freq)
                    days_until_due = (due_date - today).days
                    is_overdue = days_until_due < 0
                else:
                    is_overdue = True

                result.append(
                    {
                        "policy_id": str(policy["id"]),
                        "title": policy["title"],
                        "required": policy["acknowledgment_required"],
                        "acknowledged": acknowledged,
                        "acknowledged_at": acknowledged_at,
                        "is_overdue": is_overdue,
                        "days_until_due": days_until_due,
                    }
                )
            return result

    async def get_overdue_acknowledgments(
        self, pool: asyncpg.Pool, tenant_id: str
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT
                    e.employee_id,
                    e.full_name,
                    e.email,
                    p.id          AS policy_id,
                    p.title       AS policy_title,
                    p.acknowledgment_frequency_days,
                    MAX(pa.acknowledged_at) AS last_acked_at
                FROM employees e
                CROSS JOIN policies p
                LEFT JOIN policy_acknowledgments pa
                    ON pa.tenant_id   = e.tenant_id
                    AND pa.policy_id  = p.id::text
                    AND pa.employee_id = e.employee_id
                WHERE e.tenant_id = $1
                  AND e.employment_status = 'active'
                  AND p.tenant_id = $1
                  AND p.is_active = TRUE
                  AND p.acknowledgment_required = TRUE
                  AND (
                        'all' = ANY(p.applies_to_roles)
                        OR e.job_role = ANY(p.applies_to_roles)
                  )
                GROUP BY e.employee_id, e.full_name, e.email,
                         p.id, p.title, p.acknowledgment_frequency_days
                HAVING
                    MAX(pa.acknowledged_at) IS NULL
                    OR MAX(pa.acknowledged_at) < NOW() - (p.acknowledgment_frequency_days || ' days')::INTERVAL
                ORDER BY e.full_name, p.title
                """,
                tenant_id,
            )
            return [dict(r) for r in rows]

    async def get_policy_compliance_rate(
        self, pool: asyncpg.Pool, tenant_id: str
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            # Per-policy compliance
            rows = await conn.fetch(
                """
                WITH required AS (
                    SELECT
                        p.id AS policy_id,
                        p.title,
                        COUNT(DISTINCT e.employee_id) AS total_required
                    FROM policies p
                    CROSS JOIN employees e
                    WHERE p.tenant_id = $1
                      AND e.tenant_id = $1
                      AND p.is_active = TRUE
                      AND p.acknowledgment_required = TRUE
                      AND e.employment_status = 'active'
                      AND (
                            'all' = ANY(p.applies_to_roles)
                            OR e.job_role = ANY(p.applies_to_roles)
                      )
                    GROUP BY p.id, p.title
                ),
                acked AS (
                    SELECT
                        pa.policy_id::uuid AS policy_id,
                        COUNT(DISTINCT pa.employee_id) AS acked_count
                    FROM policy_acknowledgments pa
                    JOIN policies p ON p.id = pa.policy_id::uuid
                    WHERE pa.tenant_id = $1
                      AND pa.acknowledged_at >= NOW() - (p.acknowledgment_frequency_days || ' days')::INTERVAL
                    GROUP BY pa.policy_id
                )
                SELECT
                    r.policy_id,
                    r.title,
                    COALESCE(a.acked_count, 0) AS acked_count,
                    r.total_required,
                    CASE WHEN r.total_required = 0 THEN 100.0
                         ELSE ROUND(COALESCE(a.acked_count, 0)::numeric / r.total_required * 100, 1)
                    END AS pct
                FROM required r
                LEFT JOIN acked a ON a.policy_id = r.policy_id
                ORDER BY r.title
                """,
                tenant_id,
            )

            by_policy = [dict(r) for r in rows]
            if by_policy:
                overall_pct = round(
                    sum(r["pct"] for r in by_policy) / len(by_policy), 1
                )
            else:
                overall_pct = 100.0

            return {"overall_pct": overall_pct, "by_policy": by_policy}
