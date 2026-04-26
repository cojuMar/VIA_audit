from __future__ import annotations

import json
import secrets

import asyncpg

from src.db import tenant_conn
from src.encryption import TokenEncryption
from src.models import IntegrationCreate, IntegrationUpdate, OAuthTokenCreate

# Keys whose values should be encrypted at rest
_SENSITIVE_KEY_FRAGMENTS = ("token", "secret", "password", "key")


def _is_sensitive_key(k: str) -> bool:
    k_lower = k.lower()
    return any(frag in k_lower for frag in _SENSITIVE_KEY_FRAGMENTS)


def _encrypt_auth_config(auth_config: dict, encryption: TokenEncryption) -> dict:
    encrypted = {}
    for k, v in auth_config.items():
        if _is_sensitive_key(k) and isinstance(v, str) and v:
            encrypted[k] = encryption.encrypt(v)
        else:
            encrypted[k] = v
    return encrypted


def _decrypt_auth_config(auth_config: dict, encryption: TokenEncryption) -> dict:
    decrypted = {}
    for k, v in auth_config.items():
        if _is_sensitive_key(k) and isinstance(v, str) and v:
            plain = encryption.decrypt_safe(v)
            decrypted[k] = plain if plain is not None else v
        else:
            decrypted[k] = v
    return decrypted


class IntegrationManager:
    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    async def create(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        data: IntegrationCreate,
        encryption: TokenEncryption,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            # 1. Look up connector
            connector = await conn.fetchrow(
                "SELECT id, auth_type FROM connector_definitions WHERE connector_key = $1 AND is_active = true",
                data.connector_key,
            )
            if connector is None:
                raise ValueError(f"Connector '{data.connector_key}' not found or inactive")

            connector_id = connector["id"]
            auth_type = connector["auth_type"]

            # 2. Webhook secret
            webhook_secret = (
                secrets.token_urlsafe(32) if auth_type == "webhook" else None
            )

            # 3. Encrypt sensitive auth_config values
            encrypted_auth = _encrypt_auth_config(data.auth_config, encryption)

            # 4. INSERT
            row = await conn.fetchrow(
                """
                INSERT INTO tenant_integrations (
                    tenant_id,
                    connector_id,
                    integration_name,
                    auth_config,
                    field_mappings,
                    sync_schedule,
                    webhook_secret,
                    status,
                    created_at,
                    updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, 'pending', NOW(), NOW()
                )
                RETURNING *
                """,
                tenant_id,
                connector_id,
                data.integration_name,
                json.dumps(encrypted_auth),
                json.dumps(data.field_mappings),
                data.sync_schedule,
                webhook_secret,
            )
        result = dict(row)
        # Parse JSON fields returned as strings
        for field in ("auth_config", "field_mappings"):
            if isinstance(result.get(field), str):
                result[field] = json.loads(result[field])
        return result

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------
    async def list(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        status: str | None = None,
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            if status:
                rows = await conn.fetch(
                    """
                    SELECT ti.*, cd.connector_key, cd.display_name, cd.category, cd.auth_type
                    FROM tenant_integrations ti
                    JOIN connector_definitions cd ON cd.id = ti.connector_id
                    WHERE ti.tenant_id = $1 AND ti.status = $2
                    ORDER BY ti.created_at DESC
                    """,
                    tenant_id,
                    status,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT ti.*, cd.connector_key, cd.display_name, cd.category, cd.auth_type
                    FROM tenant_integrations ti
                    JOIN connector_definitions cd ON cd.id = ti.connector_id
                    WHERE ti.tenant_id = $1 AND ti.status != 'disabled'
                    ORDER BY ti.created_at DESC
                    """,
                    tenant_id,
                )
        result = []
        for row in rows:
            d = dict(row)
            for field in ("auth_config", "field_mappings"):
                if isinstance(d.get(field), str):
                    d[field] = json.loads(d[field])
            # Strip sensitive values from list view
            if isinstance(d.get("auth_config"), dict):
                d["auth_config"] = {
                    k: "***" if _is_sensitive_key(k) else v
                    for k, v in d["auth_config"].items()
                }
            result.append(d)
        return result

    # ------------------------------------------------------------------
    # Get (with connector info)
    # ------------------------------------------------------------------
    async def get(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        integration_id: str,
    ) -> dict | None:
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    ti.*,
                    cd.connector_key,
                    cd.display_name,
                    cd.category,
                    cd.auth_type,
                    cd.supported_data_types,
                    cd.description AS connector_description,
                    cd.logo_url
                FROM tenant_integrations ti
                JOIN connector_definitions cd ON cd.id = ti.connector_id
                WHERE ti.id = $1 AND ti.tenant_id = $2
                """,
                integration_id,
                tenant_id,
            )
        if row is None:
            return None
        result = dict(row)
        for field in ("auth_config", "field_mappings"):
            if isinstance(result.get(field), str):
                result[field] = json.loads(result[field])
        if isinstance(result.get("auth_config"), dict):
            result["auth_config"] = {
                k: "***" if _is_sensitive_key(k) else v
                for k, v in result["auth_config"].items()
            }
        return result

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    async def update(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        integration_id: str,
        data: IntegrationUpdate,
        encryption: TokenEncryption,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            existing = await conn.fetchrow(
                "SELECT * FROM tenant_integrations WHERE id = $1 AND tenant_id = $2",
                integration_id,
                tenant_id,
            )
            if existing is None:
                raise ValueError("Integration not found")

            ex = dict(existing)
            for field in ("auth_config", "field_mappings"):
                if isinstance(ex.get(field), str):
                    ex[field] = json.loads(ex[field])

            new_name = data.integration_name if data.integration_name is not None else ex["integration_name"]
            new_schedule = data.sync_schedule if data.sync_schedule is not None else ex["sync_schedule"]
            new_status = data.status if data.status is not None else ex["status"]
            new_field_mappings = data.field_mappings if data.field_mappings is not None else ex["field_mappings"]

            if data.auth_config is not None:
                new_auth = _encrypt_auth_config(data.auth_config, encryption)
            else:
                new_auth = ex["auth_config"]

            row = await conn.fetchrow(
                """
                UPDATE tenant_integrations
                SET
                    integration_name = $3,
                    auth_config = $4,
                    field_mappings = $5,
                    sync_schedule = $6,
                    status = $7,
                    updated_at = NOW()
                WHERE id = $1 AND tenant_id = $2
                RETURNING *
                """,
                integration_id,
                tenant_id,
                new_name,
                json.dumps(new_auth),
                json.dumps(new_field_mappings),
                new_schedule,
                new_status,
            )
        result = dict(row)
        for field in ("auth_config", "field_mappings"):
            if isinstance(result.get(field), str):
                result[field] = json.loads(result[field])
        if isinstance(result.get("auth_config"), dict):
            result["auth_config"] = {
                k: "***" if _is_sensitive_key(k) else v
                for k, v in result["auth_config"].items()
            }
        return result

    # ------------------------------------------------------------------
    # Pause / Resume / Delete
    # ------------------------------------------------------------------
    async def _set_status(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        integration_id: str,
        status: str,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                UPDATE tenant_integrations
                SET status = $3, updated_at = NOW()
                WHERE id = $1 AND tenant_id = $2
                RETURNING *
                """,
                integration_id,
                tenant_id,
                status,
            )
        if row is None:
            raise ValueError("Integration not found")
        result = dict(row)
        for field in ("auth_config", "field_mappings"):
            if isinstance(result.get(field), str):
                result[field] = json.loads(result[field])
        return result

    async def pause(self, pool: asyncpg.Pool, tenant_id: str, integration_id: str) -> dict:
        return await self._set_status(pool, tenant_id, integration_id, "paused")

    async def resume(self, pool: asyncpg.Pool, tenant_id: str, integration_id: str) -> dict:
        return await self._set_status(pool, tenant_id, integration_id, "active")

    async def delete(self, pool: asyncpg.Pool, tenant_id: str, integration_id: str) -> None:
        await self._set_status(pool, tenant_id, integration_id, "disabled")

    # ------------------------------------------------------------------
    # OAuth token storage
    # ------------------------------------------------------------------
    async def store_oauth_token(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        integration_id: str,
        token: OAuthTokenCreate,
        encryption: TokenEncryption,
    ) -> dict:
        encrypted_access = encryption.encrypt(token.access_token)
        encrypted_refresh = (
            encryption.encrypt(token.refresh_token) if token.refresh_token else None
        )

        expires_at_expr = (
            "NOW() + ($7 * interval '1 second')" if token.expires_in is not None else "NULL"
        )

        async with tenant_conn(pool, tenant_id) as conn:
            # Verify integration belongs to tenant
            exists = await conn.fetchval(
                "SELECT id FROM tenant_integrations WHERE id = $1 AND tenant_id = $2",
                integration_id,
                tenant_id,
            )
            if not exists:
                raise ValueError("Integration not found")

            if token.expires_in is not None:
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO oauth_tokens (
                        integration_id,
                        tenant_id,
                        access_token_enc,
                        refresh_token_enc,
                        token_type,
                        expires_at,
                        scope,
                        created_at,
                        updated_at
                    ) VALUES ($1, $2, $3, $4, $5, {expires_at_expr}, $6, NOW(), NOW())
                    ON CONFLICT (integration_id) DO UPDATE SET
                        access_token_enc = EXCLUDED.access_token_enc,
                        refresh_token_enc = EXCLUDED.refresh_token_enc,
                        token_type = EXCLUDED.token_type,
                        expires_at = EXCLUDED.expires_at,
                        scope = EXCLUDED.scope,
                        updated_at = NOW()
                    RETURNING *
                    """,
                    integration_id,
                    tenant_id,
                    encrypted_access,
                    encrypted_refresh,
                    token.token_type,
                    token.scope,
                    token.expires_in,
                )
            else:
                row = await conn.fetchrow(
                    """
                    INSERT INTO oauth_tokens (
                        integration_id,
                        tenant_id,
                        access_token_enc,
                        refresh_token_enc,
                        token_type,
                        expires_at,
                        scope,
                        created_at,
                        updated_at
                    ) VALUES ($1, $2, $3, $4, $5, NULL, $6, NOW(), NOW())
                    ON CONFLICT (integration_id) DO UPDATE SET
                        access_token_enc = EXCLUDED.access_token_enc,
                        refresh_token_enc = EXCLUDED.refresh_token_enc,
                        token_type = EXCLUDED.token_type,
                        expires_at = EXCLUDED.expires_at,
                        scope = EXCLUDED.scope,
                        updated_at = NOW()
                    RETURNING *
                    """,
                    integration_id,
                    tenant_id,
                    encrypted_access,
                    encrypted_refresh,
                    token.token_type,
                    token.scope,
                )

            # Mark integration as active
            await conn.execute(
                "UPDATE tenant_integrations SET status = 'active', updated_at = NOW() WHERE id = $1 AND tenant_id = $2",
                integration_id,
                tenant_id,
            )

        return dict(row)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------
    async def get_sync_stats(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        integration_id: str,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            # Verify ownership
            exists = await conn.fetchval(
                "SELECT id FROM tenant_integrations WHERE id = $1 AND tenant_id = $2",
                integration_id,
                tenant_id,
            )
            if not exists:
                raise ValueError("Integration not found")

            total_syncs = await conn.fetchval(
                "SELECT COUNT(*) FROM integration_sync_logs WHERE integration_id = $1",
                integration_id,
            ) or 0

            last_sync = await conn.fetchval(
                "SELECT MAX(started_at) FROM integration_sync_logs WHERE integration_id = $1",
                integration_id,
            )

            success_count = await conn.fetchval(
                "SELECT COUNT(*) FROM integration_sync_logs WHERE integration_id = $1 AND status = 'success'",
                integration_id,
            ) or 0

            success_rate = (
                round((success_count / total_syncs) * 100, 1) if total_syncs > 0 else 0.0
            )

            total_records = await conn.fetchval(
                "SELECT COALESCE(SUM(records_synced), 0) FROM integration_sync_logs WHERE integration_id = $1",
                integration_id,
            ) or 0

            last_7_days = await conn.fetchval(
                """
                SELECT COUNT(*) FROM integration_sync_logs
                WHERE integration_id = $1
                  AND started_at >= NOW() - INTERVAL '7 days'
                """,
                integration_id,
            ) or 0

        return {
            "total_syncs": total_syncs,
            "last_sync": last_sync.isoformat() if last_sync else None,
            "success_rate_pct": success_rate,
            "total_records": total_records,
            "last_7_days_syncs": last_7_days,
        }

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    async def get_integration_summary(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM tenant_integrations WHERE tenant_id = $1 AND status != 'disabled'",
                tenant_id,
            ) or 0

            status_rows = await conn.fetch(
                """
                SELECT status, COUNT(*) AS cnt
                FROM tenant_integrations
                WHERE tenant_id = $1 AND status != 'disabled'
                GROUP BY status
                """,
                tenant_id,
            )
            by_status = {r["status"]: r["cnt"] for r in status_rows}

            category_rows = await conn.fetch(
                """
                SELECT cd.category, COUNT(*) AS cnt
                FROM tenant_integrations ti
                JOIN connector_definitions cd ON cd.id = ti.connector_id
                WHERE ti.tenant_id = $1 AND ti.status != 'disabled'
                GROUP BY cd.category
                """,
                tenant_id,
            )
            by_category = {r["category"]: r["cnt"] for r in category_rows}

            last_sync_errors = await conn.fetchval(
                """
                SELECT COUNT(*) FROM integration_sync_logs isl
                JOIN tenant_integrations ti ON ti.id = isl.integration_id
                WHERE ti.tenant_id = $1
                  AND isl.status = 'failed'
                  AND isl.started_at >= NOW() - INTERVAL '24 hours'
                """,
                tenant_id,
            ) or 0

        return {
            "total": total,
            "by_status": by_status,
            "by_category": by_category,
            "last_sync_errors": last_sync_errors,
        }
