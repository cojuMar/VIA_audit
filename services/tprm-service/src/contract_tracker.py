"""
Contract & SLA Tracker

Manages vendor contracts: storage, expiry tracking, SLA commitments.
Generates renewal alerts for contracts expiring within notice period.
"""
import logging
import json
from uuid import UUID
from datetime import date, timedelta
from typing import List

logger = logging.getLogger(__name__)


class ContractTracker:
    def __init__(self, db_pool):
        self._pool = db_pool

    async def add_contract(self, tenant_id: UUID, vendor_id: UUID, contract_data: dict) -> UUID:
        """Insert a new vendor contract record."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant_id))
            contract_id = await conn.fetchval("""
                INSERT INTO vendor_contracts
                    (tenant_id, vendor_id, contract_type, title, effective_date, expiry_date,
                     auto_renews, renewal_notice_days, contract_value, currency, sla_commitments, notes)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12)
                RETURNING id
            """,
                tenant_id, vendor_id,
                contract_data['contract_type'], contract_data['title'],
                contract_data.get('effective_date'), contract_data.get('expiry_date'),
                contract_data.get('auto_renews', False), contract_data.get('renewal_notice_days', 90),
                contract_data.get('contract_value'), contract_data.get('currency', 'USD'),
                json.dumps(contract_data.get('sla_commitments', {})), contract_data.get('notes')
            )
        return contract_id

    async def get_expiring_contracts(self, tenant_id: UUID, days_ahead: int = 90) -> List[dict]:
        """
        Return all active contracts expiring within days_ahead days.
        Includes SLA commitments and auto-renewal status.
        """
        threshold = date.today() + timedelta(days=days_ahead)
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant_id))
            rows = await conn.fetch("""
                SELECT vc.*, v.name as vendor_name
                FROM vendor_contracts vc
                JOIN vendors v ON v.id = vc.vendor_id
                WHERE vc.tenant_id = $1
                  AND vc.expiry_date IS NOT NULL
                  AND vc.expiry_date <= $2
                  AND v.status = 'active'
                ORDER BY vc.expiry_date ASC
            """, tenant_id, threshold)
            return [dict(r) for r in rows]

    async def get_vendor_contracts(self, tenant_id: UUID, vendor_id: UUID) -> List[dict]:
        """Get all contracts for a specific vendor."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant_id))
            rows = await conn.fetch("""
                SELECT * FROM vendor_contracts
                WHERE tenant_id = $1 AND vendor_id = $2
                ORDER BY effective_date DESC NULLS LAST
            """, tenant_id, vendor_id)
            return [dict(r) for r in rows]
