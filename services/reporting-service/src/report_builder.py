"""
Report Builder — aggregates data from the database into a ReportRequest.

Queries:
1. Evidence records for the tenant+period → extract financial facts
2. Journal entries (from ledger connectors) → JournalEntry objects
3. Audit narratives → narrative text blocks
4. Entity info (from tenants + white_label_configs tables)
"""

import logging
from datetime import date
from typing import List, Optional
import asyncpg
from .models import FinancialFact, ReportEntity, ReportRequest

logger = logging.getLogger(__name__)


class ReportBuilder:
    """Builds ReportRequest from database evidence for a tenant+period."""

    def __init__(self, db_pool: asyncpg.Pool):
        self._pool = db_pool

    async def build(
        self,
        tenant_id: str,
        framework: str,
        period_start: date,
        period_end: date,
        narrative_ids: Optional[List[str]] = None,
    ) -> ReportRequest:
        """Build a complete ReportRequest from DB data.

        Args:
            tenant_id: Tenant UUID for RLS scoping
            framework: Compliance framework
            period_start/end: Report period
            narrative_ids: Optional specific narrative IDs to include

        Returns:
            ReportRequest ready for any generator.
        """
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)

            # Get entity info from tenants table
            tenant_row = await conn.fetchrow(
                "SELECT tenant_name FROM tenants WHERE tenant_id = $1::uuid", tenant_id
            )
            entity_name = tenant_row['tenant_name'] if tenant_row else f"Tenant {tenant_id[:8]}"

            # Get financial facts from ledger evidence records
            fact_rows = await conn.fetch("""
                SELECT
                    canonical_payload->'metadata'->>'account_code' AS account_code,
                    canonical_payload->'metadata'->>'account_name' AS account_name,
                    canonical_payload->'metadata'->>'amount' AS amount,
                    canonical_payload->'metadata'->>'currency' AS currency,
                    canonical_payload->'metadata'->>'debit_credit' AS debit_credit,
                    canonical_payload->'metadata'->>'gifi_code' AS gifi_code,
                    canonical_payload->'metadata'->>'xbrl_concept' AS xbrl_concept,
                    canonical_payload->>'entity_id' AS entity_id,
                    canonical_payload->>'timestamp_utc' AS timestamp_utc
                FROM evidence_records
                WHERE tenant_id = $1::uuid
                  AND source_system = 'quickbooks_ledger'
                  AND canonical_payload->>'event_type' = 'ledger.journal_entry'
                  AND (canonical_payload->>'timestamp_utc')::date BETWEEN $2 AND $3
                ORDER BY canonical_payload->>'timestamp_utc'
            """, tenant_id, period_start, period_end)

            # Get audit narratives
            narrative_rows = []
            if narrative_ids:
                narrative_rows = await conn.fetch("""
                    SELECT narrative_id, framework, control_id, raw_narrative,
                           combined_score, period_start, period_end
                    FROM audit_narratives
                    WHERE narrative_id = ANY($1::uuid[]) AND tenant_id = $2::uuid
                """, [nid for nid in narrative_ids], tenant_id)
            else:
                narrative_rows = await conn.fetch("""
                    SELECT narrative_id, framework, control_id, raw_narrative,
                           combined_score, period_start, period_end
                    FROM audit_narratives
                    WHERE tenant_id = $1::uuid
                      AND framework = $2
                      AND period_start >= $3 AND period_end <= $4
                      AND hitl_required = FALSE
                    ORDER BY created_at DESC
                    LIMIT 20
                """, tenant_id, framework, period_start, period_end)

        # Build financial facts
        facts: List[FinancialFact] = []
        for row in fact_rows:
            if not row['account_code'] or not row['amount']:
                continue
            try:
                facts.append(FinancialFact(
                    account_code=row['account_code'],
                    account_name=row['account_name'] or row['account_code'],
                    period_start=period_start,
                    period_end=period_end,
                    amount=float(row['amount']),
                    currency=row['currency'] or 'USD',
                    debit_credit=row['debit_credit'] or 'D',
                    entity_id=row['entity_id'] or '',
                    gifi_code=row['gifi_code'],
                    xbrl_concept=row['xbrl_concept'],
                ))
            except (ValueError, TypeError) as e:
                logger.warning("Skipping malformed fact row: %s", e)

        entity = ReportEntity(
            entity_id=tenant_id[:20],
            entity_name=entity_name,
            country="US",
            currency="USD",
            fiscal_year_end="12-31",
        )

        return ReportRequest(
            tenant_id=tenant_id,
            entity=entity,
            framework=framework,
            period_start=period_start,
            period_end=period_end,
            facts=facts,
            narratives=[dict(r) for r in narrative_rows],
            report_title=f"{framework.upper()} Report — {period_start} to {period_end}",
        )
