"""
Hallucination guardrail for AI-generated audit narratives.

Implements a RAGAS-inspired scoring pipeline:
  - Faithfulness:  |claims supported by context| / |total extracted claims|
  - Groundedness:  1 - |claims with no context support| / |total claims|
  - Combined:      harmonic mean of faithfulness and groundedness

When combined_score < HITL_THRESHOLD (0.45), the narrative is escalated to
the HITL queue before being returned to the caller.

Design notes:
  - Claim extraction uses Claude claude-haiku-4-5-20251001 (fast, cheap) to enumerate
    factual assertions in the narrative.
  - Each claim is verified against the retrieved context chunks using
    sentence-level NLI via Claude haiku — faster than full semantic search.
  - Results are deterministic for identical inputs (temperature=0 throughout).
  - Never raises — returns a GuardrailResult with hitl_required=True on error
    so that pipeline failures are conservative (escalate, never approve blindly).
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional
import anthropic
from .config import settings
from .retriever import RetrievedChunk

logger = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"  # Fast model for claim extraction/verification

CLAIM_EXTRACTION_PROMPT = """Extract all factual claims from the following audit narrative.
A "claim" is any specific factual assertion that could be verified against evidence.
Do not include general statements, framework descriptions, or methodology notes.

Return ONLY a JSON array of claim strings. Example:
["User alice performed PutObject on bucket secure-bucket at 10:00 UTC", "Access was denied for GetObject"]

Narrative:
{narrative}

JSON array of claims:"""

CLAIM_VERIFICATION_PROMPT = """Does the following evidence context support the claim below?

Claim: {claim}

Evidence context:
{context}

Answer with exactly one word: "YES" if the context directly supports the claim, "NO" if it does not.
Do not explain. Just YES or NO."""


@dataclass
class ClaimVerification:
    claim: str
    supported: bool
    supporting_citation: Optional[int]  # Citation rank that supports it, or None
    confidence: float  # 0.0–1.0


@dataclass
class GuardrailResult:
    """Result of the hallucination guardrail check.

    Attributes:
        faithfulness_score:  Fraction of claims grounded in cited evidence [0, 1]
        groundedness_score:  Fraction of claims not introducing new facts [0, 1]
        combined_score:      Harmonic mean of faithfulness and groundedness [0, 1]
        hitl_required:       True if combined_score < HITL_THRESHOLD
        flagged_claims:      Claims that failed verification (for HITL reviewer)
        verified_claims:     All claim verifications (for audit trail)
        total_claims:        Number of claims extracted
        supported_claims:    Number of claims with evidence support
        error:               Non-None if the guardrail encountered an error
                             (conservative: hitl_required=True on error)
    """
    faithfulness_score: float
    groundedness_score: float
    combined_score: float
    hitl_required: bool
    flagged_claims: List[dict] = field(default_factory=list)
    verified_claims: List[ClaimVerification] = field(default_factory=list)
    total_claims: int = 0
    supported_claims: int = 0
    error: Optional[str] = None


def _harmonic_mean(a: float, b: float) -> float:
    """Harmonic mean of two values. Returns 0 if either is 0."""
    if a <= 0 or b <= 0:
        return 0.0
    return 2 * a * b / (a + b)


def _build_context_string(chunks: List[RetrievedChunk]) -> str:
    """Build a compact context string for claim verification."""
    parts = []
    for chunk in chunks:
        parts.append(f"[CITATION:{chunk.rank}] {chunk.chunk_text}")
    return '\n\n'.join(parts)


class HallucinationGuardrail:
    """RAGAS-inspired hallucination detection for audit narratives.

    Operates in three phases:
    1. Claim extraction — enumerate factual claims in the narrative (Haiku)
    2. Claim verification — check each claim against context chunks (Haiku, parallel)
    3. Score aggregation — compute faithfulness, groundedness, combined score

    Conservative failure mode: any API error → hitl_required=True, combined_score=0.0.
    This ensures no hallucinated narrative bypasses review due to a network blip.
    """

    def __init__(self):
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def check(
        self,
        narrative: str,
        context_chunks: List[RetrievedChunk],
    ) -> GuardrailResult:
        """Run the hallucination guardrail on a generated narrative.

        Args:
            narrative: The AI-generated audit narrative text
            context_chunks: The retrieved evidence chunks used as context

        Returns:
            GuardrailResult with scores and HITL decision.
            Never raises — errors produce conservative (hitl_required=True) result.
        """
        try:
            return await self._check_internal(narrative, context_chunks)
        except Exception as e:
            logger.error("Hallucination guardrail error (conservative fail): %s", e, exc_info=True)
            return GuardrailResult(
                faithfulness_score=0.0,
                groundedness_score=0.0,
                combined_score=0.0,
                hitl_required=True,
                error=f"Guardrail error: {type(e).__name__}: {e}",
            )

    async def _check_internal(
        self,
        narrative: str,
        context_chunks: List[RetrievedChunk],
    ) -> GuardrailResult:
        # Phase 1: Extract claims
        claims = await self._extract_claims(narrative)

        if not claims:
            # No claims extracted — short narrative or extraction failure
            # Conservative: treat as unverifiable → escalate
            logger.warning("No claims extracted from narrative (len=%d chars)", len(narrative))
            return GuardrailResult(
                faithfulness_score=0.0,
                groundedness_score=0.0,
                combined_score=0.0,
                hitl_required=True,
                total_claims=0,
                supported_claims=0,
                error="No claims extracted — narrative may be too short or malformed",
            )

        # Phase 2: Verify claims against context (parallel, max 10 concurrent)
        context_str = _build_context_string(context_chunks)
        verifications = await self._verify_claims_parallel(claims, context_str, context_chunks)

        # Phase 3: Score aggregation
        total = len(verifications)
        supported = sum(1 for v in verifications if v.supported)
        unsupported = total - supported

        faithfulness = supported / total if total > 0 else 0.0
        # Groundedness: same metric from the claim perspective
        # (in RAGAS, groundedness = answer_relevance; here we use symmetric metric)
        groundedness = 1.0 - (unsupported / total) if total > 0 else 0.0
        combined = _harmonic_mean(faithfulness, groundedness)

        hitl_required = combined < settings.hallucination_threshold

        flagged = [
            {
                "claim": v.claim,
                "issue": "not_grounded_in_evidence",
                "score": v.confidence,
            }
            for v in verifications if not v.supported
        ]

        result = GuardrailResult(
            faithfulness_score=round(faithfulness, 3),
            groundedness_score=round(groundedness, 3),
            combined_score=round(combined, 3),
            hitl_required=hitl_required,
            flagged_claims=flagged,
            verified_claims=verifications,
            total_claims=total,
            supported_claims=supported,
        )

        if hitl_required:
            logger.warning(
                "HITL escalation triggered: combined_score=%.3f < threshold=%.2f "
                "(%d/%d claims unsupported)",
                combined, settings.hallucination_threshold, unsupported, total
            )

        return result

    async def _extract_claims(self, narrative: str) -> List[str]:
        """Use Claude Haiku to extract verifiable factual claims."""
        prompt = CLAIM_EXTRACTION_PROMPT.format(narrative=narrative)
        try:
            message = await self._client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=512,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            # Extract JSON array from response
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            if not match:
                return []
            claims = json.loads(match.group(0))
            return [c for c in claims if isinstance(c, str) and len(c.strip()) > 10]
        except (json.JSONDecodeError, IndexError, Exception) as e:
            logger.warning("Claim extraction failed: %s", e)
            return []

    async def _verify_single_claim(
        self,
        claim: str,
        context_str: str,
        context_chunks: List[RetrievedChunk],
        semaphore: asyncio.Semaphore,
    ) -> ClaimVerification:
        """Verify a single claim against the context."""
        async with semaphore:
            prompt = CLAIM_VERIFICATION_PROMPT.format(claim=claim, context=context_str)
            try:
                message = await self._client.messages.create(
                    model=HAIKU_MODEL,
                    max_tokens=5,
                    temperature=0,
                    messages=[{"role": "user", "content": prompt}],
                )
                answer = message.content[0].text.strip().upper()
                supported = answer.startswith("YES")

                # Find which citation supports it (simple keyword overlap heuristic)
                supporting_citation = None
                if supported:
                    for chunk in context_chunks:
                        claim_words = set(claim.lower().split())
                        chunk_words = set(chunk.chunk_text.lower().split())
                        if len(claim_words & chunk_words) >= 3:
                            supporting_citation = chunk.rank
                            break

                return ClaimVerification(
                    claim=claim,
                    supported=supported,
                    supporting_citation=supporting_citation,
                    confidence=1.0 if answer in ("YES", "NO") else 0.5,
                )
            except Exception as e:
                logger.warning("Claim verification failed for '%s...': %s", claim[:50], e)
                # Conservative: unsupported on error
                return ClaimVerification(
                    claim=claim,
                    supported=False,
                    supporting_citation=None,
                    confidence=0.0,
                )

    async def _verify_claims_parallel(
        self,
        claims: List[str],
        context_str: str,
        context_chunks: List[RetrievedChunk],
    ) -> List[ClaimVerification]:
        """Verify all claims in parallel with concurrency limit."""
        semaphore = asyncio.Semaphore(10)  # Max 10 concurrent Haiku calls
        tasks = [
            self._verify_single_claim(claim, context_str, context_chunks, semaphore)
            for claim in claims
        ]
        return await asyncio.gather(*tasks)
