from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import asyncpg
import structlog

from .models import TenantCreate, TenantResponse, TenantTier

logger = structlog.get_logger(__name__)


def _schema_name(tenant_id: str, tier: TenantTier) -> str:
    if tier == TenantTier.ENTERPRISE_SILO:
        return f"tenant_{tenant_id.replace('-', '_')}"
    return "public"


class TenantProvisioner:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def provision_tenant(self, req: TenantCreate) -> TenantResponse:
        tenant_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        schema = _schema_name(tenant_id, req.tier)

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SET LOCAL row_security = off")

                if req.tier == TenantTier.SMB_POOL:
                    # Insert into shared pool schema
                    await conn.execute(
                        """
                        INSERT INTO public.tenants (
                            tenant_id, display_name, tier, region,
                            external_id, schema_name, is_active, created_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, TRUE, $7)
                        """,
                        tenant_id,
                        req.display_name,
                        req.tier.value,
                        req.region,
                        req.external_id,
                        schema,
                        now,
                    )
                    # Bootstrap chain sequence counter for this tenant
                    await conn.execute(
                        """
                        INSERT INTO public.chain_sequence_counters
                            (tenant_id, counter_name, sequence_value, updated_at)
                        VALUES ($1, 'audit_log', 0, $2)
                        ON CONFLICT DO NOTHING
                        """,
                        tenant_id,
                        now,
                    )
                else:
                    # Enterprise silo: delegate to stored procedure
                    await conn.execute(
                        "SELECT provision_enterprise_tenant($1, $2, $3)",
                        tenant_id,
                        req.display_name,
                        req.region,
                    )
                    # Record in canonical tenants table
                    await conn.execute(
                        """
                        INSERT INTO public.tenants (
                            tenant_id, display_name, tier, region,
                            external_id, schema_name, is_active, created_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, TRUE, $7)
                        ON CONFLICT DO NOTHING
                        """,
                        tenant_id,
                        req.display_name,
                        req.tier.value,
                        req.region,
                        req.external_id,
                        schema,
                        now,
                    )

        logger.info(
            "tenant_provisioned",
            tenant_id=tenant_id,
            tier=req.tier.value,
            region=req.region,
        )

        return TenantResponse(
            tenant_id=tenant_id,
            external_id=req.external_id,
            display_name=req.display_name,
            tier=req.tier,
            region=req.region,
            is_active=True,
            created_at=now,
            schema_name=schema,
        )

    async def deprovision_tenant(self, tenant_id: str) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SET LOCAL row_security = off")

                row = await conn.fetchrow(
                    "SELECT tier FROM public.tenants WHERE tenant_id = $1",
                    tenant_id,
                )
                if row is None:
                    raise ValueError(f"Tenant '{tenant_id}' not found")

                tier = TenantTier(row["tier"])

                if tier == TenantTier.ENTERPRISE_SILO:
                    await conn.execute(
                        "SELECT deprovision_enterprise_tenant($1)", tenant_id
                    )
                else:
                    # Soft-delete for pool tenants
                    await conn.execute(
                        """
                        UPDATE public.tenants
                        SET is_active = FALSE, deprovisioned_at = NOW()
                        WHERE tenant_id = $1
                        """,
                        tenant_id,
                    )

        logger.info("tenant_deprovisioned", tenant_id=tenant_id)

    async def create_firm_bridge_view(
        self, firm_tenant_id: str, client_tenant_ids: list[str]
    ) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SET LOCAL row_security = off")
                await conn.execute(
                    "SELECT create_firm_bridge_view($1, $2::uuid[])",
                    firm_tenant_id,
                    client_tenant_ids,
                )
        logger.info(
            "firm_bridge_view_created",
            firm_tenant_id=firm_tenant_id,
            client_count=len(client_tenant_ids),
        )

    async def get_tenant(self, tenant_id: str) -> Optional[TenantResponse]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT tenant_id, display_name, tier, region, external_id,
                       schema_name, is_active, created_at
                FROM public.tenants
                WHERE tenant_id = $1
                """,
                tenant_id,
            )
        if row is None:
            return None

        return TenantResponse(
            tenant_id=row["tenant_id"],
            external_id=row["external_id"],
            display_name=row["display_name"],
            tier=TenantTier(row["tier"]),
            region=row["region"],
            is_active=row["is_active"],
            created_at=row["created_at"],
            schema_name=row["schema_name"],
        )

    async def list_tenants(
        self,
        tier: Optional[TenantTier] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TenantResponse]:
        async with self._pool.acquire() as conn:
            if tier is not None:
                rows = await conn.fetch(
                    """
                    SELECT tenant_id, display_name, tier, region, external_id,
                           schema_name, is_active, created_at
                    FROM public.tenants
                    WHERE tier = $1
                    ORDER BY created_at DESC
                    LIMIT $2 OFFSET $3
                    """,
                    tier.value,
                    limit,
                    offset,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT tenant_id, display_name, tier, region, external_id,
                           schema_name, is_active, created_at
                    FROM public.tenants
                    ORDER BY created_at DESC
                    LIMIT $1 OFFSET $2
                    """,
                    limit,
                    offset,
                )

        return [
            TenantResponse(
                tenant_id=row["tenant_id"],
                external_id=row["external_id"],
                display_name=row["display_name"],
                tier=TenantTier(row["tier"]),
                region=row["region"],
                is_active=row["is_active"],
                created_at=row["created_at"],
                schema_name=row["schema_name"],
            )
            for row in rows
        ]
