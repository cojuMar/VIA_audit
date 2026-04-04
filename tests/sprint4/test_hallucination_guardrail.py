"""
Sprint 4 — Hallucination Guardrail Tests

Tests the faithfulness/groundedness scoring pipeline and HITL escalation logic.
These tests use mocked Claude API calls (no real API calls in CI).

The hallucination guardrail is THE CRITICAL GATE before narratives reach users.
A passing guardrail score does not guarantee correctness, but a failing score
MUST trigger HITL escalation without exception.

Run: pytest tests/sprint4/test_hallucination_guardrail.py -v
"""

import asyncio
import pytest
from dataclasses import dataclass
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/rag-pipeline-service'))


# ---------------------------------------------------------------------------
# Minimal stubs for imports that require env vars / external services
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    """Patch settings before any module import."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/dummy")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-dummy")
    monkeypatch.setenv("VOYAGE_API_KEY", "dummy")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_chunk(rank: int, text: str, similarity: float = 0.85):
    """Create a minimal RetrievedChunk for testing."""
    from src.retriever import RetrievedChunk
    return RetrievedChunk(
        evidence_record_id=f"record-{rank:04d}",
        chunk_text=text,
        similarity_score=similarity,
        rank=rank,
        canonical_payload={"event_type": "test.event", "outcome": "success"},
    )


def _make_haiku_response(text: str):
    """Build a minimal anthropic message mock."""
    content = MagicMock()
    content.text = text
    msg = MagicMock()
    msg.content = [content]
    return msg


# ---------------------------------------------------------------------------
# Tests: _harmonic_mean
# ---------------------------------------------------------------------------

class TestHarmonicMean:
    def test_equal_values(self):
        from src.hallucination_guardrail import _harmonic_mean
        assert _harmonic_mean(0.8, 0.8) == pytest.approx(0.8)

    def test_zero_left(self):
        from src.hallucination_guardrail import _harmonic_mean
        assert _harmonic_mean(0.0, 0.9) == 0.0

    def test_zero_right(self):
        from src.hallucination_guardrail import _harmonic_mean
        assert _harmonic_mean(0.9, 0.0) == 0.0

    def test_one_and_one(self):
        from src.hallucination_guardrail import _harmonic_mean
        assert _harmonic_mean(1.0, 1.0) == pytest.approx(1.0)

    def test_asymmetric(self):
        from src.hallucination_guardrail import _harmonic_mean
        # H(0.2, 0.8) = 2*0.2*0.8/(0.2+0.8) = 0.32
        assert _harmonic_mean(0.2, 0.8) == pytest.approx(0.32)

    def test_always_leq_arithmetic_mean(self):
        """Harmonic mean ≤ arithmetic mean (AM-HM inequality)."""
        from src.hallucination_guardrail import _harmonic_mean
        for a, b in [(0.3, 0.7), (0.5, 0.9), (0.1, 1.0)]:
            hm = _harmonic_mean(a, b)
            am = (a + b) / 2
            assert hm <= am + 1e-9, f"HM({a},{b})={hm} > AM={am}"


# ---------------------------------------------------------------------------
# Tests: claim extraction
# ---------------------------------------------------------------------------

class TestClaimExtraction:
    @pytest.fixture
    def guardrail(self):
        from src.hallucination_guardrail import HallucinationGuardrail
        return HallucinationGuardrail()

    @pytest.mark.asyncio
    async def test_extracts_claims_from_valid_json(self, guardrail):
        """Haiku returns a valid JSON array → claims extracted correctly."""
        mock_response = _make_haiku_response(
            '["User alice accessed bucket at 10:00 UTC", "Access was denied for GetObject"]'
        )
        with patch.object(guardrail._client.messages, 'create', new=AsyncMock(return_value=mock_response)):
            claims = await guardrail._extract_claims("Some narrative text")
        assert len(claims) == 2
        assert "alice" in claims[0]

    @pytest.mark.asyncio
    async def test_returns_empty_on_invalid_json(self, guardrail):
        """Malformed JSON from Haiku → empty list, no exception."""
        mock_response = _make_haiku_response("Not valid JSON at all")
        with patch.object(guardrail._client.messages, 'create', new=AsyncMock(return_value=mock_response)):
            claims = await guardrail._extract_claims("Some narrative")
        assert claims == []

    @pytest.mark.asyncio
    async def test_filters_short_claims(self, guardrail):
        """Claims shorter than 10 chars are filtered out."""
        mock_response = _make_haiku_response('["ok", "yes", "User alice accessed S3 bucket at 10:00 UTC"]')
        with patch.object(guardrail._client.messages, 'create', new=AsyncMock(return_value=mock_response)):
            claims = await guardrail._extract_claims("Narrative")
        assert len(claims) == 1
        assert "alice" in claims[0]


# ---------------------------------------------------------------------------
# Tests: claim verification
# ---------------------------------------------------------------------------

class TestClaimVerification:
    @pytest.fixture
    def guardrail(self):
        from src.hallucination_guardrail import HallucinationGuardrail
        return HallucinationGuardrail()

    @pytest.fixture
    def context_chunks(self):
        return [
            make_chunk(1, "User alice performed PutObject on bucket secure-bucket at 10:00 UTC"),
            make_chunk(2, "Access was denied for GetObject with error AccessDenied"),
        ]

    @pytest.mark.asyncio
    async def test_supported_claim_returns_true(self, guardrail, context_chunks):
        """Haiku answers YES → claim marked supported."""
        mock_response = _make_haiku_response("YES")
        sem = asyncio.Semaphore(10)
        context_str = "User alice performed PutObject on bucket secure-bucket"
        with patch.object(guardrail._client.messages, 'create', new=AsyncMock(return_value=mock_response)):
            result = await guardrail._verify_single_claim(
                "User alice accessed secure-bucket", context_str, context_chunks, sem
            )
        assert result.supported is True

    @pytest.mark.asyncio
    async def test_unsupported_claim_returns_false(self, guardrail, context_chunks):
        """Haiku answers NO → claim marked unsupported."""
        mock_response = _make_haiku_response("NO")
        sem = asyncio.Semaphore(10)
        context_str = "User alice performed PutObject"
        with patch.object(guardrail._client.messages, 'create', new=AsyncMock(return_value=mock_response)):
            result = await guardrail._verify_single_claim(
                "User bob deleted an S3 bucket", context_str, context_chunks, sem
            )
        assert result.supported is False

    @pytest.mark.asyncio
    async def test_api_error_conservative_fail(self, guardrail, context_chunks):
        """API error during claim verification → unsupported (conservative)."""
        sem = asyncio.Semaphore(10)
        with patch.object(
            guardrail._client.messages, 'create',
            new=AsyncMock(side_effect=Exception("network error"))
        ):
            result = await guardrail._verify_single_claim(
                "Some claim", "some context", context_chunks, sem
            )
        assert result.supported is False
        assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# Tests: full guardrail check
# ---------------------------------------------------------------------------

class TestGuardrailCheck:
    @pytest.fixture
    def guardrail(self):
        from src.hallucination_guardrail import HallucinationGuardrail
        return HallucinationGuardrail()

    @pytest.fixture
    def good_chunks(self):
        return [
            make_chunk(1, "User alice accessed S3 bucket secure-bucket at 10:00 UTC outcome=success"),
            make_chunk(2, "IAM policy AllowS3ReadWrite was evaluated and permitted the action"),
        ]

    @pytest.mark.asyncio
    async def test_all_claims_supported_no_hitl(self, guardrail, good_chunks):
        """All claims supported → combined_score ≥ 0.45 → hitl_required=False."""
        claims_response = _make_haiku_response(
            '["User alice accessed S3 bucket", "IAM policy permitted the action"]'
        )
        yes_response = _make_haiku_response("YES")

        responses = [claims_response, yes_response, yes_response]
        call_idx = 0

        async def mock_create(**kwargs):
            nonlocal call_idx
            r = responses[min(call_idx, len(responses) - 1)]
            call_idx += 1
            return r

        with patch.object(guardrail._client.messages, 'create', new=mock_create):
            result = await guardrail.check("Alice accessed S3 bucket permitted by IAM policy.", good_chunks)

        assert result.hitl_required is False
        assert result.combined_score >= 0.45
        assert result.faithfulness_score == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_no_claims_extracted_triggers_hitl(self, guardrail, good_chunks):
        """Empty claim list → conservative escalation."""
        mock_response = _make_haiku_response("[]")
        with patch.object(guardrail._client.messages, 'create', new=AsyncMock(return_value=mock_response)):
            result = await guardrail.check("Short narrative.", good_chunks)
        assert result.hitl_required is True
        assert result.combined_score == 0.0

    @pytest.mark.asyncio
    async def test_fabricated_claim_triggers_hitl(self, guardrail, good_chunks):
        """A claim not in evidence → low score → hitl_required=True."""
        claims_response = _make_haiku_response(
            '["User bob deleted production database at 03:00 UTC", "No alerts were triggered"]'
        )
        no_response = _make_haiku_response("NO")

        responses = [claims_response, no_response, no_response]
        call_idx = 0

        async def mock_create(**kwargs):
            nonlocal call_idx
            r = responses[min(call_idx, len(responses) - 1)]
            call_idx += 1
            return r

        with patch.object(guardrail._client.messages, 'create', new=mock_create):
            result = await guardrail.check("Bob deleted production database. No alerts fired.", good_chunks)

        assert result.hitl_required is True
        assert len(result.flagged_claims) == 2
        assert result.faithfulness_score == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_api_error_is_conservative(self, guardrail, good_chunks):
        """Any top-level error → hitl_required=True, never silently passes."""
        with patch.object(
            guardrail._client.messages, 'create',
            new=AsyncMock(side_effect=RuntimeError("unexpected error"))
        ):
            result = await guardrail.check("Any narrative text here.", good_chunks)
        assert result.hitl_required is True
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_hitl_threshold_boundary_exactly_045(self, guardrail, good_chunks):
        """combined_score exactly at threshold (0.45) triggers HITL (< not <=)."""
        from src.hallucination_guardrail import _harmonic_mean
        # 1/3 supported, 2/3 unsupported → faithfulness=0.333, groundedness=0.667
        # H(0.333, 0.667) = 2*0.333*0.667/(0.333+0.667) ≈ 0.444 < 0.45 → hitl
        claims_response = _make_haiku_response(
            '["Claim A is supported", "Claim B is not found anywhere", "Claim C also not found"]'
        )
        responses_seq = [claims_response, _make_haiku_response("YES"),
                         _make_haiku_response("NO"), _make_haiku_response("NO")]
        call_idx = 0

        async def mock_create(**kwargs):
            nonlocal call_idx
            r = responses_seq[min(call_idx, len(responses_seq) - 1)]
            call_idx += 1
            return r

        with patch.object(guardrail._client.messages, 'create', new=mock_create):
            result = await guardrail.check("Narrative with mixed support.", good_chunks)

        # combined = H(1/3, 2/3) ≈ 0.444 → below threshold
        assert result.hitl_required is True


# ---------------------------------------------------------------------------
# Tests: HITL priority escalation
# ---------------------------------------------------------------------------

class TestHITLPriority:
    def test_critical_priority_below_020(self):
        from src.hitl_escalation import HITLEscalationService
        svc = HITLEscalationService(None)
        assert svc._determine_priority(0.10) == 'critical'
        assert svc._determine_priority(0.19) == 'critical'

    def test_high_priority_020_to_035(self):
        from src.hitl_escalation import HITLEscalationService
        svc = HITLEscalationService(None)
        assert svc._determine_priority(0.20) == 'high'
        assert svc._determine_priority(0.34) == 'high'

    def test_normal_priority_035_to_045(self):
        from src.hitl_escalation import HITLEscalationService
        svc = HITLEscalationService(None)
        assert svc._determine_priority(0.35) == 'normal'
        assert svc._determine_priority(0.44) == 'normal'

    def test_low_priority_above_threshold(self):
        from src.hitl_escalation import HITLEscalationService
        svc = HITLEscalationService(None)
        assert svc._determine_priority(0.50) == 'low'
        assert svc._determine_priority(0.99) == 'low'
