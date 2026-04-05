import hashlib
import json
import logging
from dataclasses import dataclass
from typing import List, Optional
import asyncpg
from .claude_client import ClaudeAuditClient
from .config import settings
from .embedder import EvidenceEmbedder
from .hallucination_guardrail import GuardrailResult, HallucinationGuardrail
from .hitl_escalation import HITLEscalationService
from .prompt_builder import AuditPromptBuilder
from .retriever import EvidenceRetriever, RetrievedChunk

logger = logging.getLogger(__name__)


@dataclass
class NarrativeResult:
    narrative_id: str
    narrative: str
    faithfulness_score: float
    groundedness_score: float
    combined_score: float
    hitl_required: bool
    hitl_queue_id: Optional[str]
    citation_count: int
    generation_latency_ms: int


class AuditNarrator:
    """Orchestrates the full RAG pipeline for audit narrative generation.

    Pipeline:
      1. Embed the audit query (framework + control + period)
      2. Retrieve top-K relevant evidence chunks
      3. Build structured prompt with embedded citations
      4. Generate narrative via Claude
      5. Run hallucination guardrail (faithfulness + groundedness)
      6. Persist narrative + citations + guardrail scores to DB
      7. If hitl_required: enqueue in HITL queue
      8. Return NarrativeResult

    Tenant isolation: every DB operation uses SET LOCAL app.tenant_id for RLS.
    """

    def __init__(self, db_pool: asyncpg.Pool):
        self._pool = db_pool
        self._embedder = EvidenceEmbedder()
        self._retriever = EvidenceRetriever(db_pool)
        self._prompt_builder = AuditPromptBuilder()
        self._claude = ClaudeAuditClient()
        self._guardrail = HallucinationGuardrail()
        self._hitl = HITLEscalationService(db_pool)

    async def generate(
        self,
        tenant_id: str,
        framework: str,
        control_id: Optional[str],
        period_start: str,
        period_end: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> NarrativeResult:
        """Generate a guardrail-checked audit narrative for a compliance control.

        Args:
            tenant_id: Tenant UUID for RLS scoping
            framework: 'soc2', 'iso27001', 'pci_dss', or 'custom'
            control_id: Control identifier (e.g. 'CC6.1') or None for general
            period_start/end: Audit period dates (ISO format: 'YYYY-MM-DD')
            date_from/to: Optional evidence date range filter

        Returns:
            NarrativeResult with narrative text, scores, and HITL status.
        """
        # Step 1: Build query text and embed it
        query_text = self._build_query_text(framework, control_id, period_start, period_end)
        query_embedding = await self._embedder.embed_query(query_text)

        # Step 2: Retrieve relevant evidence
        chunks = await self._retriever.retrieve(
            query_embedding=query_embedding,
            tenant_id=tenant_id,
            date_from=date_from,
            date_to=date_to,
        )

        logger.info(
            "Retrieved %d chunks for tenant=%s framework=%s control=%s",
            len(chunks), tenant_id[:8], framework, control_id
        )

        # Step 3: Build prompt
        prompt = self._prompt_builder.build(
            framework=framework,
            control_id=control_id,
            period_start=period_start,
            period_end=period_end,
            chunks=chunks,
        )

        # Step 4: Generate narrative
        gen_result = await self._claude.generate_narrative(prompt)

        # Step 5: Run hallucination guardrail
        guardrail_result = await self._guardrail.check(
            narrative=gen_result.narrative,
            context_chunks=chunks,
        )

        # Step 6: Persist to DB
        narrative_id = await self._persist(
            tenant_id=tenant_id,
            framework=framework,
            control_id=control_id,
            period_start=period_start,
            period_end=period_end,
            narrative=gen_result.narrative,
            guardrail=guardrail_result,
            chunks=chunks,
            gen_result=gen_result,
        )

        # Step 7: HITL escalation if required
        hitl_queue_id = None
        if guardrail_result.hitl_required and settings.hitl_escalation_enabled:
            hitl_queue_id = await self._hitl.escalate(
                narrative_id=narrative_id,
                tenant_id=tenant_id,
                guardrail_result=guardrail_result,
            )

        return NarrativeResult(
            narrative_id=narrative_id,
            narrative=gen_result.narrative,
            faithfulness_score=guardrail_result.faithfulness_score,
            groundedness_score=guardrail_result.groundedness_score,
            combined_score=guardrail_result.combined_score,
            hitl_required=guardrail_result.hitl_required,
            hitl_queue_id=hitl_queue_id,
            citation_count=len(chunks),
            generation_latency_ms=gen_result.latency_ms,
        )

    def _build_query_text(
        self,
        framework: str,
        control_id: Optional[str],
        period_start: str,
        period_end: str,
    ) -> str:
        """Build the query text used to retrieve relevant evidence."""
        parts = [f"Audit evidence for {framework}"]
        if control_id:
            parts.append(f"control {control_id}")
        parts.append(f"period {period_start} to {period_end}")
        return " ".join(parts)

    async def _persist(
        self,
        tenant_id: str,
        framework: str,
        control_id: Optional[str],
        period_start: str,
        period_end: str,
        narrative: str,
        guardrail: GuardrailResult,
        chunks: List[RetrievedChunk],
        gen_result,
    ) -> str:
        """Persist narrative, citations, and guardrail scores to PostgreSQL."""
        import json

        prompt_hash = hashlib.sha256(
            f"{framework}:{control_id}:{period_start}:{period_end}:{tenant_id}".encode()
        ).digest()

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute('SELECT set_config('app.tenant_id', $1, false)', tenant_id)

                narrative_id = await conn.fetchval("""
                    INSERT INTO audit_narratives (
                        tenant_id, framework, control_id, period_start, period_end,
                        prompt_hash, raw_narrative,
                        faithfulness_score, groundedness_score, combined_score,
                        hitl_required, generation_model, generation_latency_ms
                    ) VALUES (
                        $1::uuid, $2, $3, $4::date, $5::date,
                        $6, $7,
                        $8, $9, $10,
                        $11, $12, $13
                    ) RETURNING narrative_id::text
                """,
                    tenant_id, framework, control_id, period_start, period_end,
                    prompt_hash, narrative,
                    guardrail.faithfulness_score, guardrail.groundedness_score, guardrail.combined_score,
                    guardrail.hitl_required, gen_result.model, gen_result.latency_ms,
                )

                # Insert citations
                for chunk in chunks:
                    await conn.execute("""
                        INSERT INTO rag_citations (
                            narrative_id, evidence_record_id, tenant_id,
                            similarity_score, citation_rank, chunk_text
                        ) VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6)
                        ON CONFLICT (narrative_id, evidence_record_id) DO NOTHING
                    """,
                        narrative_id, chunk.evidence_record_id, tenant_id,
                        chunk.similarity_score, chunk.rank, chunk.chunk_text,
                    )

        return narrative_id
