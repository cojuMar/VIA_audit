import logging
from uuid import UUID
import asyncpg
from .hallucination_guardrail import GuardrailResult

logger = logging.getLogger(__name__)


class HITLEscalationService:
    """Inserts low-confidence narratives into the hitl_narrative_queue.

    Called by AuditNarrator when guardrail.hitl_required is True.
    Determines priority based on combined_score:
      - score < 0.20 → critical
      - score < 0.35 → high
      - score < 0.45 → normal (at threshold boundary)
    """

    PRIORITY_THRESHOLDS = [
        (0.20, 'critical'),
        (0.35, 'high'),
        (0.45, 'normal'),
    ]

    def __init__(self, db_pool: asyncpg.Pool):
        self._pool = db_pool

    def _determine_priority(self, combined_score: float) -> str:
        for threshold, priority in self.PRIORITY_THRESHOLDS:
            if combined_score < threshold:
                return priority
        return 'low'  # Above threshold — should not normally be called

    async def escalate(
        self,
        narrative_id: str,
        tenant_id: str,
        guardrail_result: GuardrailResult,
    ) -> str:
        """Insert narrative into HITL queue. Returns queue_id."""
        import json
        priority = self._determine_priority(guardrail_result.combined_score)

        reason = (
            f"combined_score={guardrail_result.combined_score:.3f} < "
            f"threshold={0.45:.2f}; "
            f"faithfulness={guardrail_result.faithfulness_score:.3f}; "
            f"groundedness={guardrail_result.groundedness_score:.3f}; "
            f"{len(guardrail_result.flagged_claims)} unsupported claims"
        )
        if guardrail_result.error:
            reason += f"; error={guardrail_result.error}"

        async with self._pool.acquire() as conn:
            await conn.execute('SET LOCAL app.tenant_id = $1', tenant_id)
            queue_id = await conn.fetchval("""
                INSERT INTO hitl_narrative_queue
                    (narrative_id, tenant_id, escalation_reason, flagged_claims, priority)
                VALUES ($1::uuid, $2::uuid, $3, $4::jsonb, $5)
                RETURNING queue_id::text
            """,
                narrative_id,
                tenant_id,
                reason,
                json.dumps(guardrail_result.flagged_claims),
                priority,
            )

        logger.info(
            "HITL escalation queued: narrative=%s priority=%s score=%.3f",
            narrative_id, priority, guardrail_result.combined_score
        )
        return queue_id
