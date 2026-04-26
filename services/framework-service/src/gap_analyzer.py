"""
Gap Analyzer — Identifies framework control gaps for a tenant.

A gap exists when:
- A tenant has activated a framework
- A control in that framework has no tenant_control_evidence row,
  OR the evidence status is 'not_started' or 'failing'

Gap severity is determined by:
- is_key_control=TRUE + status=failing → CRITICAL
- is_key_control=TRUE + status=not_started → HIGH
- is_key_control=FALSE + status=failing → MEDIUM
- is_key_control=FALSE + status=not_started → LOW
"""
import logging
from typing import List
from uuid import UUID
from .models import GapItem, GapSeverity
import anthropic

logger = logging.getLogger(__name__)


class GapAnalyzer:
    def __init__(self, db_pool, anthropic_api_key: str = ""):
        self._pool = db_pool
        self._anthropic_client = anthropic.AsyncAnthropic(api_key=anthropic_api_key) if anthropic_api_key else None

    async def analyze(self, tenant_id: UUID, framework_id: UUID) -> List[GapItem]:
        """
        Full gap analysis for one tenant+framework combination.
        Returns list of GapItems sorted by severity (critical first).
        """
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant_id))

            rows = await conn.fetch("""
                SELECT
                    fc.id as framework_control_id,
                    fc.control_id,
                    fc.title,
                    fc.domain,
                    fc.is_key_control,
                    fc.description,
                    COALESCE(tce.status, 'not_started') as status
                FROM framework_controls fc
                LEFT JOIN tenant_control_evidence tce ON (
                    tce.framework_control_id = fc.id
                    AND tce.tenant_id = $1
                )
                WHERE fc.framework_id = $2
                  AND COALESCE(tce.status, 'not_started') IN ('not_started', 'failing')
                ORDER BY fc.is_key_control DESC, fc.control_id
            """, tenant_id, framework_id)

            gaps = []
            for row in rows:
                severity = self._compute_severity(row['is_key_control'], row['status'])
                remediation = await self._suggest_remediation(row['control_id'], row['title'], row['description'])
                gaps.append(GapItem(
                    framework_control_id=row['framework_control_id'],
                    control_id=row['control_id'],
                    control_title=row['title'],
                    domain=row['domain'],
                    gap_severity=severity,
                    gap_description=f"Control '{row['control_id']}' is {row['status']}.",
                    remediation_steps=remediation
                ))

            # Persist gap items
            async with conn.transaction():
                # Clear old unresolved gaps for this framework+tenant
                await conn.execute("""
                    DELETE FROM framework_gap_items
                    WHERE tenant_id = $1 AND framework_id = $2 AND resolved_at IS NULL
                """, tenant_id, framework_id)

                for gap in gaps:
                    await conn.execute("""
                        INSERT INTO framework_gap_items
                            (tenant_id, framework_id, framework_control_id, gap_severity, gap_description, remediation_steps)
                        VALUES ($1, $2, $3, $4, $5, $6)
                    """, tenant_id, framework_id, gap.framework_control_id,
                        gap.gap_severity.value, gap.gap_description, gap.remediation_steps)

            return gaps

    def _compute_severity(self, is_key: bool, status: str) -> GapSeverity:
        if is_key and status == 'failing':
            return GapSeverity.CRITICAL
        if is_key and status == 'not_started':
            return GapSeverity.HIGH
        if not is_key and status == 'failing':
            return GapSeverity.MEDIUM
        return GapSeverity.LOW

    async def _suggest_remediation(self, control_id: str, title: str, description: str) -> str:
        """Use Claude Haiku to suggest remediation steps. Falls back to generic if no API key."""
        if not self._anthropic_client:
            return f"Implement controls to satisfy: {title}. Collect required evidence and link to this control."

        try:
            response = await self._anthropic_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                temperature=0,
                messages=[{
                    "role": "user",
                    "content": f"Provide 3 concise remediation steps for compliance control {control_id}: '{title}'. Description: {description[:200]}. Format as numbered list, max 150 words."
                }]
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.warning(f"Claude remediation suggestion failed: {e}")
            return f"Implement controls to satisfy: {title}. Collect required evidence and link to this control."
