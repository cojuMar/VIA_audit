"""
Fourth-Party Risk Visibility

Identifies and risk-scores sub-processors two levels deep.
(Your vendor's critical vendors.)

Sources:
1. Vendor-declared sub_processors field (from intake form)
2. Vendor document analysis (sub-processors mentioned in SOC 2 reports)
3. Manual additions via API

Provides a simple graph view: Tenant → Vendor → Sub-Processor
"""
import logging
from uuid import UUID
from typing import List, Dict

logger = logging.getLogger(__name__)


class FourthPartyAnalyzer:
    def __init__(self, db_pool):
        self._pool = db_pool

    async def sync_from_vendor(self, tenant_id: UUID, vendor_id: UUID) -> int:
        """
        Sync sub_processors from vendor record into fourth_party_relationships.
        Returns count of new relationships added.
        """
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant_id))
            vendor = await conn.fetchrow(
                "SELECT sub_processors FROM vendors WHERE id = $1 AND tenant_id = $2",
                vendor_id, tenant_id
            )
            if not vendor or not vendor['sub_processors']:
                return 0

            added = 0
            for sub_name in vendor['sub_processors']:
                result = await conn.execute("""
                    INSERT INTO fourth_party_relationships
                        (tenant_id, parent_vendor_id, sub_processor_name)
                    VALUES ($1, $2, $3)
                    ON CONFLICT DO NOTHING
                """, tenant_id, vendor_id, sub_name)
                if result != "INSERT 0 0":
                    added += 1
            return added

    async def get_fourth_party_graph(self, tenant_id: UUID) -> Dict:
        """
        Return the full vendor → sub-processor graph for a tenant.
        Format: {vendor_name: [sub_processor_names]}
        """
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant_id))
            rows = await conn.fetch("""
                SELECT v.name as vendor_name, fpr.sub_processor_name,
                       fpr.risk_tier, fpr.is_verified
                FROM fourth_party_relationships fpr
                JOIN vendors v ON v.id = fpr.parent_vendor_id
                WHERE fpr.tenant_id = $1
                ORDER BY v.name, fpr.sub_processor_name
            """, tenant_id)

            graph = {}
            for row in rows:
                vname = row['vendor_name']
                if vname not in graph:
                    graph[vname] = []
                graph[vname].append({
                    "name": row['sub_processor_name'],
                    "risk_tier": row['risk_tier'],
                    "is_verified": row['is_verified']
                })
            return graph

    async def add_relationship(self, tenant_id: UUID, parent_vendor_id: UUID,
                                sub_processor_name: str, risk_tier: str = 'unrated',
                                data_types: List[str] = None) -> UUID:
        """Manually add a fourth-party relationship."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant_id))
            rel_id = await conn.fetchval("""
                INSERT INTO fourth_party_relationships
                    (tenant_id, parent_vendor_id, sub_processor_name, risk_tier, data_types_shared)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            """, tenant_id, parent_vendor_id, sub_processor_name, risk_tier, data_types or [])
        return rel_id
