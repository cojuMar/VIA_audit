"""
Sprint 4 — RAG Pipeline Tests

Tests for prompt building, embedding text construction, and claim extraction
utilities. All tests are offline (no external API calls).

Run: pytest tests/sprint4/test_rag_pipeline.py -v
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/rag-pipeline-service'))


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/dummy")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-dummy")
    monkeypatch.setenv("VOYAGE_API_KEY", "dummy")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")


def make_chunk(rank, text, similarity=0.85):
    from src.retriever import RetrievedChunk
    return RetrievedChunk(
        evidence_record_id=f"rec-{rank:04d}",
        chunk_text=text,
        similarity_score=similarity,
        rank=rank,
        canonical_payload={"event_type": "test"},
    )


# ---------------------------------------------------------------------------
# Prompt builder tests
# ---------------------------------------------------------------------------

class TestPromptBuilder:
    @pytest.fixture
    def builder(self):
        from src.prompt_builder import AuditPromptBuilder
        return AuditPromptBuilder()

    def test_prompt_contains_framework_label(self, builder):
        chunks = [make_chunk(1, "Test evidence")]
        prompt = builder.build("soc2", "CC6.1", "2026-01-01", "2026-03-31", chunks)
        assert "SOC 2 Type II" in prompt.user_prompt

    def test_prompt_contains_control_id(self, builder):
        chunks = [make_chunk(1, "Test evidence")]
        prompt = builder.build("iso27001", "A.9.1.2", "2026-01-01", "2026-03-31", chunks)
        assert "A.9.1.2" in prompt.user_prompt

    def test_prompt_contains_citations(self, builder):
        chunks = [
            make_chunk(1, "Alice accessed bucket"),
            make_chunk(2, "Bob updated IAM policy"),
        ]
        prompt = builder.build("soc2", "CC6.1", "2026-01-01", "2026-03-31", chunks)
        assert "[CITATION:1]" in prompt.user_prompt
        assert "[CITATION:2]" in prompt.user_prompt

    def test_system_prompt_prohibits_amounts(self, builder):
        """System prompt must instruct Claude not to disclose amounts (ZK private inputs)."""
        from src.prompt_builder import SYSTEM_PROMPT
        assert "amount" in SYSTEM_PROMPT.lower() or "financial" in SYSTEM_PROMPT.lower()
        # Must tell Claude NOT to include amounts
        assert "not" in SYSTEM_PROMPT.lower() or "do not" in SYSTEM_PROMPT.lower()

    def test_prompt_context_chunks_attribute(self, builder):
        chunks = [make_chunk(1, "Evidence text")]
        prompt = builder.build("pci_dss", None, "2026-01-01", "2026-03-31", chunks)
        assert prompt.context_chunks == chunks
        assert len(prompt.context_chunks) == 1

    def test_token_estimate_is_positive(self, builder):
        chunks = [make_chunk(1, "Evidence")]
        prompt = builder.build("soc2", "CC6.1", "2026-01-01", "2026-03-31", chunks)
        assert prompt.token_estimate > 0


# ---------------------------------------------------------------------------
# Embedder text construction tests (no API call)
# ---------------------------------------------------------------------------

class TestEvidenceTextConstruction:
    @pytest.fixture
    def embedder(self):
        from src.embedder import EvidenceEmbedder
        import voyageai
        from unittest.mock import patch, MagicMock
        with patch.object(voyageai, 'AsyncClient', return_value=MagicMock()):
            return EvidenceEmbedder()

    def test_text_includes_event_type(self, embedder):
        payload = {"event_type": "aws.putobject", "entity_id": "e1",
                   "entity_type": "aws_resource", "timestamp_utc": "2026-04-01T10:00:00Z",
                   "outcome": "success"}
        text = embedder.evidence_record_to_text(payload)
        assert "aws.putobject" in text

    def test_text_excludes_amount(self, embedder):
        """Amounts must never appear in embeddable text (ZK private input isolation)."""
        payload = {"event_type": "transaction.created", "entity_id": "txn-001",
                   "entity_type": "financial_transaction", "outcome": "success",
                   "timestamp_utc": "2026-04-01T11:00:00Z"}
        metadata = {"amount": 99999.99, "currency": "USD", "merchant_name": "ACME"}
        text = embedder.evidence_record_to_text(payload, metadata)
        assert "99999" not in text
        assert "amount" not in text.lower()
        assert "ACME" in text  # non-sensitive metadata IS included

    def test_text_includes_actor(self, embedder):
        payload = {"event_type": "iam.policy_update", "entity_id": "policy-01",
                   "entity_type": "iam_policy", "outcome": "success",
                   "timestamp_utc": "2026-04-01T09:00:00Z",
                   "actor_id": "alice@example.com"}
        text = embedder.evidence_record_to_text(payload)
        assert "alice@example.com" in text

    def test_truncation_at_word_boundary(self, embedder):
        from src.embedder import _truncate_to_tokens
        long_text = "word " * 10000  # very long
        truncated = _truncate_to_tokens(long_text, max_tokens=100)
        assert len(truncated) <= 100 * 4 + 10  # approximate
        assert not truncated.endswith(" word")[::-1].startswith("d")  # doesn't mid-word cut
        # Should end on word boundary (space before last word removed)
        assert " " not in truncated[-1:]  # last char is not a space (stripped)

    def test_short_text_not_truncated(self, embedder):
        from src.embedder import _truncate_to_tokens
        short = "This is a short text."
        assert _truncate_to_tokens(short) == short


# ---------------------------------------------------------------------------
# Guardrail integration: amount never in narrative
# ---------------------------------------------------------------------------

class TestAmountIsolationInNarrative:
    """CRITICAL: Verify the system prompt prevents Claude from disclosing amounts."""

    def test_system_prompt_has_amount_prohibition(self):
        from src.prompt_builder import SYSTEM_PROMPT
        # The system prompt must explicitly mention not disclosing amounts
        lower = SYSTEM_PROMPT.lower()
        assert any(phrase in lower for phrase in [
            "do not disclose",
            "not disclose",
            "must not appear",
            "private input",
            "do not include",
        ]), "System prompt must explicitly prohibit amount disclosure"

    def test_evidence_text_excludes_all_financial_fields(self):
        """All financial amount fields are stripped during evidence text construction."""
        from src.embedder import EvidenceEmbedder
        import voyageai
        from unittest.mock import patch, MagicMock
        with patch.object(voyageai, 'AsyncClient', return_value=MagicMock()):
            embedder = EvidenceEmbedder()

        payload = {"event_type": "ledger.entry", "entity_id": "je-001",
                   "entity_type": "journal_entry", "outcome": "success",
                   "timestamp_utc": "2026-04-01T14:00:00Z"}
        metadata = {
            "amount": 150000.00,
            "balance": 2000000.00,
            "credit": 150000.00,
            "debit": 0.00,
            "account_name": "Revenue",  # safe
        }
        text = embedder.evidence_record_to_text(payload, metadata)

        for forbidden in ["150000", "2000000", "balance", "credit", "debit"]:
            assert forbidden not in text, f"'{forbidden}' found in evidence text — ZK isolation broken"
        assert "Revenue" in text  # safe field is preserved
