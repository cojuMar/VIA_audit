import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

import httpx
import asyncpg

from src.db import tenant_conn
from src.encryption import TokenEncryption
from src.models import SyncRequest


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SyncEngine:
    def __init__(self, settings, encryption: TokenEncryption):
        self.settings = settings
        self.encryption = encryption
        self.http = httpx.AsyncClient(timeout=30.0)

    # ------------------------------------------------------------------
    # Main sync orchestrator
    # ------------------------------------------------------------------
    async def run_sync(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        integration_id: str,
        sync_request: SyncRequest,
    ) -> dict:
        started_at = datetime.now(timezone.utc)
        total_records = 0
        errors: list[str] = []
        synced_types: list[str] = []

        async with tenant_conn(pool, tenant_id) as conn:
            # 1. Load integration + connector
            row = await conn.fetchrow(
                """
                SELECT ti.*, cd.connector_key, cd.supported_data_types, cd.auth_type
                FROM tenant_integrations ti
                JOIN connector_definitions cd ON cd.id = ti.connector_id
                WHERE ti.id = $1 AND ti.tenant_id = $2
                """,
                integration_id,
                tenant_id,
            )
            if row is None:
                raise ValueError("Integration not found")

            integration = dict(row)
            for field in ("auth_config", "field_mappings"):
                if isinstance(integration.get(field), str):
                    integration[field] = json.loads(integration[field])

            # 3. Decrypt auth_config
            auth_config = {}
            for k, v in integration.get("auth_config", {}).items():
                if isinstance(v, str) and v:
                    plain = self.encryption.decrypt_safe(v)
                    auth_config[k] = plain if plain is not None else v
                else:
                    auth_config[k] = v

            supported_types: list[str] = integration.get("supported_data_types") or []
            data_types = sync_request.data_types if sync_request.data_types else supported_types
            if not data_types:
                data_types = ["records"]  # generic fallback

            # Field mappings per data_type
            field_mappings: dict = integration.get("field_mappings", {})

            # 4. Sync each data_type
            for dt in data_types:
                try:
                    raw_records = await self._fetch_data(integration, dt, auth_config)
                    mappings = field_mappings.get(dt, [])

                    for raw in raw_records:
                        normalized = await self._normalize_record(
                            raw, integration["connector_key"], dt, mappings
                        )
                        record_id = str(uuid.uuid4())
                        await conn.execute(
                            """
                            INSERT INTO integration_records (
                                id,
                                integration_id,
                                tenant_id,
                                data_type,
                                source_record_id,
                                raw_data,
                                normalized_data,
                                synced_at
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
                            """,
                            record_id,
                            integration_id,
                            tenant_id,
                            dt,
                            str(raw.get("id", record_id)),
                            json.dumps(raw),
                            json.dumps(normalized),
                        )
                        total_records += 1
                    synced_types.append(dt)
                except Exception as exc:
                    errors.append(f"{dt}: {exc!s}")

        # Determine final status
        if errors and not synced_types:
            final_status = "failed"
        elif errors:
            final_status = "partial"
        else:
            final_status = "success"

        completed_at = datetime.now(timezone.utc)

        # 5. INSERT final sync_log (immutable — insert only)
        async with tenant_conn(pool, tenant_id) as conn:
            log_id = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO integration_sync_logs (
                    id,
                    integration_id,
                    tenant_id,
                    sync_type,
                    status,
                    started_at,
                    completed_at,
                    records_synced,
                    error_message,
                    data_types_synced
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                log_id,
                integration_id,
                tenant_id,
                sync_request.sync_type,
                final_status,
                started_at,
                completed_at,
                total_records,
                "; ".join(errors) if errors else None,
                json.dumps(synced_types),
            )

            # 6. UPDATE tenant_integrations (mutable)
            await conn.execute(
                """
                UPDATE tenant_integrations
                SET
                    last_sync_at = $2,
                    last_sync_status = $3,
                    last_sync_record_count = $4,
                    updated_at = NOW()
                WHERE id = $1
                """,
                integration_id,
                completed_at,
                final_status,
                total_records,
            )

        # 7. Return summary
        return {
            "sync_log_id": log_id,
            "status": final_status,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "records_synced": total_records,
            "data_types_synced": synced_types,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Synthetic data fetcher (dev mode)
    # ------------------------------------------------------------------
    async def _fetch_data(
        self,
        integration: dict,
        data_type: str,
        auth_config: dict,
    ) -> list[dict]:
        now = _now_iso()

        if data_type == "employees":
            return [
                {
                    "id": f"emp-{i:04d}",
                    "first_name": name.split()[0],
                    "last_name": name.split()[1],
                    "email": f"{name.split()[0].lower()}.{name.split()[1].lower()}@example.com",
                    "department": dept,
                    "title": title,
                    "hire_date": "2022-01-15",
                    "status": "active",
                    "created_at": now,
                }
                for i, (name, dept, title) in enumerate(
                    [
                        ("Alice Johnson", "Engineering", "Software Engineer"),
                        ("Bob Smith", "Finance", "Financial Analyst"),
                        ("Carol White", "HR", "HR Manager"),
                        ("David Brown", "Engineering", "Senior Engineer"),
                        ("Eve Davis", "Marketing", "Marketing Lead"),
                    ],
                    start=1,
                )
            ]

        if data_type == "iam_users":
            return [
                {
                    "id": f"iam-{i:04d}",
                    "username": uname,
                    "email": f"{uname}@example.com",
                    "roles": roles,
                    "mfa_enabled": mfa,
                    "last_login": "2026-04-01T10:00:00Z",
                    "status": "active",
                    "created_at": now,
                }
                for i, (uname, roles, mfa) in enumerate(
                    [
                        ("alice.j", ["developer", "read-only"], True),
                        ("bob.s", ["analyst"], False),
                        ("carol.w", ["hr-admin"], True),
                        ("david.b", ["developer", "deployer"], True),
                        ("eve.d", ["marketing"], False),
                    ],
                    start=1,
                )
            ]

        if data_type == "gl_transactions":
            return [
                {
                    "id": f"txn-{i:04d}",
                    "date": "2026-03-31",
                    "account_code": acct,
                    "description": desc,
                    "debit": debit,
                    "credit": credit,
                    "currency": "USD",
                    "posted": True,
                    "created_at": now,
                }
                for i, (acct, desc, debit, credit) in enumerate(
                    [
                        ("1000", "Cash receipt", 5000.00, 0.0),
                        ("2000", "Accounts payable", 0.0, 3200.00),
                        ("5100", "Software licenses", 1500.00, 0.0),
                        ("4000", "Revenue", 0.0, 8000.00),
                        ("6000", "Payroll expense", 12000.00, 0.0),
                        ("1100", "Bank transfer", 0.0, 5000.00),
                        ("3000", "Owner equity", 0.0, 2000.00),
                        ("5200", "Office supplies", 250.00, 0.0),
                        ("1200", "Receivables", 8000.00, 0.0),
                        ("2100", "Accrued liabilities", 0.0, 1500.00),
                    ],
                    start=1,
                )
            ]

        if data_type == "invoices":
            return [
                {
                    "id": f"inv-{i:04d}",
                    "vendor": vendor,
                    "amount": amount,
                    "currency": "USD",
                    "issue_date": "2026-03-01",
                    "due_date": "2026-04-01",
                    "status": status,
                    "line_items": [{"description": "Service", "qty": 1, "unit_price": amount}],
                    "created_at": now,
                }
                for i, (vendor, amount, status) in enumerate(
                    [
                        ("Acme Corp", 4500.00, "paid"),
                        ("TechVendor Inc", 1200.00, "pending"),
                        ("Cloud Services Ltd", 800.00, "overdue"),
                        ("Consulting Group", 7500.00, "paid"),
                        ("Office Supplies Co", 320.00, "pending"),
                    ],
                    start=1,
                )
            ]

        if data_type == "incidents":
            return [
                {
                    "id": f"inc-{i:04d}",
                    "title": title,
                    "severity": severity,
                    "status": status,
                    "assigned_to": assignee,
                    "created_by": "system",
                    "created_at": now,
                    "resolved_at": None,
                }
                for i, (title, severity, status, assignee) in enumerate(
                    [
                        ("Database connection timeout", "high", "open", "david.b"),
                        ("Login page slow", "medium", "investigating", "alice.j"),
                        ("Email delivery failure", "low", "resolved", "carol.w"),
                        ("API rate limit exceeded", "high", "open", "david.b"),
                        ("SSL certificate expiry warning", "medium", "open", "alice.j"),
                    ],
                    start=1,
                )
            ]

        if data_type == "s3_buckets":
            return [
                {
                    "id": f"bucket-{i:04d}",
                    "name": name,
                    "region": region,
                    "versioning_enabled": versioning,
                    "public_access_blocked": True,
                    "encryption": "AES-256",
                    "created_at": now,
                }
                for i, (name, region, versioning) in enumerate(
                    [
                        ("prod-data-lake", "us-east-1", True),
                        ("dev-artifacts", "us-west-2", False),
                        ("audit-logs-archive", "eu-west-1", True),
                    ],
                    start=1,
                )
            ]

        if data_type == "vulnerabilities":
            return [
                {
                    "id": f"vuln-{i:04d}",
                    "cve_id": cve,
                    "severity": severity,
                    "cvss_score": score,
                    "affected_package": pkg,
                    "status": status,
                    "discovered_at": now,
                    "remediated_at": None,
                }
                for i, (cve, severity, score, pkg, status) in enumerate(
                    [
                        ("CVE-2026-1001", "critical", 9.8, "openssl@3.0.1", "open"),
                        ("CVE-2026-1042", "high", 7.5, "log4j@2.14.1", "mitigated"),
                        ("CVE-2025-9981", "medium", 5.3, "requests@2.27.1", "open"),
                        ("CVE-2026-0033", "low", 3.1, "pillow@9.0.0", "resolved"),
                        ("CVE-2026-2210", "critical", 9.1, "nginx@1.20.1", "open"),
                    ],
                    start=1,
                )
            ]

        if data_type == "users":
            return [
                {
                    "id": f"usr-{i:04d}",
                    "username": uname,
                    "email": f"{uname}@example.com",
                    "full_name": fullname,
                    "is_active": True,
                    "last_login": "2026-04-01T09:00:00Z",
                    "created_at": now,
                }
                for i, (uname, fullname) in enumerate(
                    [
                        ("alice.j", "Alice Johnson"),
                        ("bob.s", "Bob Smith"),
                        ("carol.w", "Carol White"),
                        ("david.b", "David Brown"),
                        ("eve.d", "Eve Davis"),
                    ],
                    start=1,
                )
            ]

        # Default: generic records
        return [
            {"id": f"rec-{i:04d}", "name": f"Record {i}", "created_at": now}
            for i in range(1, 4)
        ]

    # ------------------------------------------------------------------
    # Field mapping / normalization
    # ------------------------------------------------------------------
    async def _normalize_record(
        self,
        raw: dict,
        connector_key: str,
        data_type: str,
        mappings: list[dict],
    ) -> dict:
        if not mappings:
            return raw

        normalized: dict = {}
        for mapping in mappings:
            source = mapping.get("source_field", "")
            target = mapping.get("target_field", "")
            transform = mapping.get("transform_fn")
            is_required = mapping.get("is_required", False)

            value = raw.get(source)

            if value is None:
                if is_required:
                    normalized[target] = None
                continue

            if transform:
                try:
                    value = self._apply_transform(raw, source, value, transform)
                except Exception:
                    pass  # keep original value on transform failure

            normalized[target] = value

        return normalized

    def _apply_transform(self, raw: dict, source_field: str, value, transform_fn: str):
        """Apply a transform expression to a field value."""
        tf = transform_fn.strip()

        # "map: A→X, B→Y"
        if tf.startswith("map:"):
            mapping_str = tf[4:].strip()
            pairs = [p.strip() for p in mapping_str.split(",")]
            value_map: dict = {}
            for pair in pairs:
                if "→" in pair:
                    k, v = pair.split("→", 1)
                    value_map[k.strip()] = v.strip()
                elif "->" in pair:
                    k, v = pair.split("->", 1)
                    value_map[k.strip()] = v.strip()
            return value_map.get(str(value), value)

        # "concat: field1 field2"
        if tf.startswith("concat:"):
            fields_str = tf[7:].strip()
            fields = fields_str.split()
            parts = [str(raw.get(f, "")) for f in fields]
            return " ".join(p for p in parts if p)

        # "expr: len(field) > 0"
        if tf.startswith("expr:"):
            expr = tf[5:].strip()
            try:
                result = eval(expr, {"__builtins__": {}}, {source_field: value, **raw})  # noqa: S307
                return result
            except Exception:
                return value

        return value

    # ------------------------------------------------------------------
    # Webhook processor
    # ------------------------------------------------------------------
    async def process_webhook(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        integration_id: str,
        event_type: str,
        payload: dict,
        headers: dict,
        source_event_id: str | None = None,
    ) -> dict:

        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Validate HMAC signature if webhook_secret is configured
        async with pool.acquire() as conn:
            secret_row = await conn.fetchrow(
                "SELECT webhook_secret FROM tenant_integrations WHERE id = $1",
                integration_id,
            )

        webhook_secret: str | None = None
        if secret_row and secret_row["webhook_secret"]:
            webhook_secret = secret_row["webhook_secret"]

        signature_valid = True
        if webhook_secret:
            sig_header = headers.get("x-hub-signature-256") or headers.get("X-Hub-Signature-256", "")
            if sig_header:
                body_bytes = json.dumps(payload, separators=(",", ":")).encode()
                expected_sig = (
                    "sha256="
                    + hmac.new(
                        webhook_secret.encode(),
                        body_bytes,
                        hashlib.sha256,
                    ).hexdigest()
                )
                signature_valid = hmac.compare_digest(sig_header, expected_sig)
            else:
                signature_valid = False

        processing_status = "processed" if signature_valid else "rejected"

        # INSERT webhook_events (immutable)
        async with tenant_conn(pool, tenant_id) as conn:
            await conn.execute(
                """
                INSERT INTO webhook_events (
                    id,
                    integration_id,
                    tenant_id,
                    event_type,
                    source_event_id,
                    payload,
                    headers,
                    processing_status,
                    received_at,
                    processed_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                event_id,
                integration_id,
                tenant_id,
                event_type,
                source_event_id,
                json.dumps(payload),
                json.dumps(headers),
                processing_status,
                now,
                now,
            )

        return {
            "event_id": event_id,
            "status": processing_status,
            "processed_at": now.isoformat(),
        }
