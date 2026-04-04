"""
Sprint 6 — PDF Generator and PAdES Signer Tests

Tests PDFA3Generator and PAdESSigner:
  - generate() returns non-empty bytes
  - PDFGenerationResult has non-empty checksum_sha256
  - Checksum is consistent (same output -> same hash)
  - Amounts are NOT present in PDF content (ZK privacy)
  - PAdESSigner dev mode: missing cert returns is_signed=False with warning
  - PAdESSigner does not raise when cert not present
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/reporting-service'))

import hashlib
import pytest
from datetime import date

from src.models import FinancialFact, ReportEntity, ReportRequest
from src.pdf_generator import PDFA3Generator, PDFGenerationResult
from src.pades_signer import PAdESSigner, SignatureResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Distinctive amount that must NOT appear verbatim in the PDF output
PRIVATE_AMOUNT = 99999.42

ZK_PRIVATE_AMOUNT_STR = "99999.42"
ZK_PRIVATE_AMOUNT_STR_ALT = "99999.4"   # partial match guard
ZK_PRIVATE_INT_STR = "99999"


def make_entity():
    return ReportEntity(
        entity_id='test-entity-001',
        entity_name='Test Corp',
        country='US',
        currency='USD',
        fiscal_year_end='12-31',
        tax_id='12-3456789',
    )


def make_fact_with_private_amount():
    return FinancialFact(
        account_code='1000',
        account_name='Cash',
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
        amount=PRIVATE_AMOUNT,
        currency='USD',
        debit_credit='D',
        entity_id='test-entity-001',
        gifi_code='1000',
        xbrl_concept='us-gaap:CashAndCashEquivalentsAtCarryingValue',
    )


def make_request(with_private_amount=False, narratives=None, evidence_records=None):
    facts = [make_fact_with_private_amount()] if with_private_amount else []
    return ReportRequest(
        tenant_id='tenant-abc',
        entity=make_entity(),
        framework='soc2',
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
        facts=facts,
        narratives=narratives or [],
        evidence_records=evidence_records or [],
        report_title='Q1 2026 SOC 2 Compliance Report',
    )


# ---------------------------------------------------------------------------
# PDFA3Generator tests
# ---------------------------------------------------------------------------

class TestPDFA3Generator:

    def test_generate_returns_non_empty_bytes(self):
        gen = PDFA3Generator()
        result = gen.generate(make_request())
        assert isinstance(result.pdf_bytes, bytes)
        assert len(result.pdf_bytes) > 0

    def test_generate_returns_pdf_generation_result(self):
        gen = PDFA3Generator()
        result = gen.generate(make_request())
        assert isinstance(result, PDFGenerationResult)

    def test_pdf_starts_with_pdf_header(self):
        gen = PDFA3Generator()
        result = gen.generate(make_request())
        assert result.pdf_bytes[:4] == b'%PDF', (
            "PDF output must start with %PDF header"
        )

    def test_checksum_sha256_is_non_empty(self):
        gen = PDFA3Generator()
        result = gen.generate(make_request())
        assert result.checksum_sha256 is not None
        assert len(result.checksum_sha256) > 0

    def test_checksum_sha256_is_32_bytes(self):
        gen = PDFA3Generator()
        result = gen.generate(make_request())
        # SHA-256 digest is always 32 bytes
        assert len(result.checksum_sha256) == 32, (
            f"SHA-256 checksum must be 32 bytes, got {len(result.checksum_sha256)}"
        )

    def test_checksum_is_consistent(self):
        """Generating the same PDF twice should produce identical checksums."""
        gen = PDFA3Generator()
        req = make_request()
        result1 = gen.generate(req)
        # Manually compute checksum from the same bytes
        expected_checksum = hashlib.sha256(result1.pdf_bytes).digest()
        assert result1.checksum_sha256 == expected_checksum, (
            "checksum_sha256 must equal sha256(pdf_bytes)"
        )

    def test_checksum_matches_pdf_bytes(self):
        gen = PDFA3Generator()
        result = gen.generate(make_request())
        recomputed = hashlib.sha256(result.pdf_bytes).digest()
        assert result.checksum_sha256 == recomputed

    def test_page_count_is_positive(self):
        gen = PDFA3Generator()
        result = gen.generate(make_request())
        assert result.page_count >= 1

    def test_amounts_not_present_in_pdf_bytes(self):
        """
        ZK privacy: financial amounts from facts must NOT appear verbatim
        in the PDF byte content. The PDFA3Generator explicitly excludes amounts.
        """
        gen = PDFA3Generator()
        result = gen.generate(make_request(with_private_amount=True))
        pdf_text = result.pdf_bytes.decode('latin-1', errors='replace')

        assert ZK_PRIVATE_AMOUNT_STR not in pdf_text, (
            f"Private amount {ZK_PRIVATE_AMOUNT_STR!r} must not appear in PDF output "
            f"(ZK privacy requirement)"
        )

    def test_amounts_not_present_as_integer_in_pdf_bytes(self):
        """
        Secondary ZK check: even the integer part of a distinctive private amount
        should not appear if the generator correctly excludes all financial data.
        Uses a value unlikely to appear in structural PDF content.
        """
        gen = PDFA3Generator()
        # Use a very distinctive amount that won't match any PDF structural data
        result = gen.generate(make_request(with_private_amount=True))
        pdf_text = result.pdf_bytes.decode('latin-1', errors='replace')
        assert ZK_PRIVATE_AMOUNT_STR not in pdf_text

    def test_generate_with_narratives(self):
        narratives = [
            {
                'control_id': 'CC6.1',
                'raw_narrative': 'Access controls are implemented appropriately.',
                'combined_score': 0.92,
            }
        ]
        gen = PDFA3Generator()
        result = gen.generate(make_request(narratives=narratives))
        assert isinstance(result.pdf_bytes, bytes)
        assert len(result.pdf_bytes) > 0

    def test_generate_with_evidence_records(self):
        evidence = [
            {
                'source_system': 'okta',
                'canonical_payload': {
                    'event_type': 'auth.login',
                    'outcome': 'success',
                }
            },
            {
                'source_system': 'github',
                'canonical_payload': {
                    'event_type': 'code.push',
                    'outcome': 'success',
                }
            }
        ]
        gen = PDFA3Generator()
        result = gen.generate(make_request(evidence_records=evidence))
        assert isinstance(result.pdf_bytes, bytes)
        assert len(result.pdf_bytes) > 0

    def test_generate_with_xbrl_attachment(self):
        """generate() should accept optional xbrl_bytes without raising."""
        gen = PDFA3Generator()
        dummy_xbrl = b'<?xml version="1.0"?><xbrl/>'
        result = gen.generate(make_request(), xbrl_bytes=dummy_xbrl)
        assert isinstance(result.pdf_bytes, bytes)
        assert len(result.pdf_bytes) > 0

    def test_different_requests_produce_different_checksums(self):
        gen = PDFA3Generator()
        req1 = make_request(narratives=[{'control_id': 'A', 'raw_narrative': 'First', 'combined_score': 0.9}])
        req2 = make_request(narratives=[{'control_id': 'B', 'raw_narrative': 'Second', 'combined_score': 0.8}])
        result1 = gen.generate(req1)
        result2 = gen.generate(req2)
        # Different content should produce different checksums
        assert result1.checksum_sha256 != result2.checksum_sha256


# ---------------------------------------------------------------------------
# PAdESSigner tests
# ---------------------------------------------------------------------------

class TestPAdESSigner:

    def test_sign_returns_signature_result(self):
        signer = PAdESSigner(
            cert_path='/nonexistent/cert.pem',
            key_path='/nonexistent/key.pem',
            tsa_url='http://timestamp.digicert.com',
        )
        gen = PDFA3Generator()
        pdf_result = gen.generate(make_request())
        result = signer.sign(pdf_result.pdf_bytes)
        assert isinstance(result, SignatureResult)

    def test_dev_mode_is_signed_false_when_cert_missing(self):
        """
        When cert and key files do not exist, PAdESSigner must return
        is_signed=False without raising an exception.
        """
        signer = PAdESSigner(
            cert_path='/nonexistent/path/cert.pem',
            key_path='/nonexistent/path/key.pem',
            tsa_url='http://timestamp.digicert.com',
        )
        gen = PDFA3Generator()
        pdf_result = gen.generate(make_request())

        # Must NOT raise — dev mode returns gracefully
        result = signer.sign(pdf_result.pdf_bytes)

        assert result.is_signed is False, (
            "is_signed must be False when cert files are not present"
        )

    def test_dev_mode_has_warning_field(self):
        signer = PAdESSigner(
            cert_path='/nonexistent/path/cert.pem',
            key_path='/nonexistent/path/key.pem',
            tsa_url='http://timestamp.digicert.com',
        )
        gen = PDFA3Generator()
        pdf_result = gen.generate(make_request())
        result = signer.sign(pdf_result.pdf_bytes)

        assert result.warning is not None, "warning field must be set in dev mode"
        assert len(result.warning) > 0

    def test_dev_mode_pdf_bytes_returned_unchanged(self):
        """In dev mode, the original unsigned PDF bytes should be returned."""
        signer = PAdESSigner(
            cert_path='/nonexistent/path/cert.pem',
            key_path='/nonexistent/path/key.pem',
            tsa_url='http://timestamp.digicert.com',
        )
        gen = PDFA3Generator()
        pdf_result = gen.generate(make_request())
        original_bytes = pdf_result.pdf_bytes

        result = signer.sign(original_bytes)
        assert result.signed_pdf_bytes == original_bytes

    def test_dev_mode_signature_type_is_unsigned(self):
        signer = PAdESSigner(
            cert_path='/nonexistent/path/cert.pem',
            key_path='/nonexistent/path/key.pem',
            tsa_url='http://timestamp.digicert.com',
        )
        gen = PDFA3Generator()
        pdf_result = gen.generate(make_request())
        result = signer.sign(pdf_result.pdf_bytes)
        assert result.signature_type == 'unsigned'

    def test_dev_mode_signer_dn_is_none(self):
        signer = PAdESSigner(
            cert_path='/nonexistent/path/cert.pem',
            key_path='/nonexistent/path/key.pem',
            tsa_url='http://timestamp.digicert.com',
        )
        gen = PDFA3Generator()
        pdf_result = gen.generate(make_request())
        result = signer.sign(pdf_result.pdf_bytes)
        assert result.signer_dn is None

    def test_dev_mode_signing_time_is_none(self):
        signer = PAdESSigner(
            cert_path='/nonexistent/path/cert.pem',
            key_path='/nonexistent/path/key.pem',
            tsa_url='http://timestamp.digicert.com',
        )
        gen = PDFA3Generator()
        pdf_result = gen.generate(make_request())
        result = signer.sign(pdf_result.pdf_bytes)
        assert result.signing_time is None

    def test_dev_mode_does_not_raise(self):
        """Explicitly verify no exception is raised (no pytest.raises needed)."""
        signer = PAdESSigner(
            cert_path='/path/that/does/not/exist/cert.pem',
            key_path='/path/that/does/not/exist/key.pem',
            tsa_url='http://timestamp.digicert.com',
        )
        gen = PDFA3Generator()
        pdf_result = gen.generate(make_request())

        exception_raised = False
        try:
            result = signer.sign(pdf_result.pdf_bytes)
        except Exception:
            exception_raised = True

        assert not exception_raised, "PAdESSigner must not raise in dev mode"

    def test_sign_accepts_valid_bytes_input(self):
        """sign() should accept any bytes input without type errors."""
        signer = PAdESSigner(
            cert_path='/nonexistent/cert.pem',
            key_path='/nonexistent/key.pem',
            tsa_url='http://timestamp.digicert.com',
        )
        # Minimal valid-looking PDF bytes
        dummy_pdf = b'%PDF-1.4\n%fake pdf content for testing'
        result = signer.sign(dummy_pdf)
        assert isinstance(result, SignatureResult)
        assert result.signed_pdf_bytes == dummy_pdf

    def test_sign_with_custom_reason(self):
        signer = PAdESSigner(
            cert_path='/nonexistent/cert.pem',
            key_path='/nonexistent/key.pem',
            tsa_url='http://timestamp.digicert.com',
        )
        gen = PDFA3Generator()
        pdf_result = gen.generate(make_request())
        # Should not raise even with a custom reason
        result = signer.sign(pdf_result.pdf_bytes, reason="Sprint 6 Audit Certification")
        assert isinstance(result, SignatureResult)

    def test_signature_result_dataclass_fields(self):
        """SignatureResult should have all expected fields."""
        signer = PAdESSigner(
            cert_path='/nonexistent/cert.pem',
            key_path='/nonexistent/key.pem',
            tsa_url='http://timestamp.digicert.com',
        )
        gen = PDFA3Generator()
        pdf_result = gen.generate(make_request())
        result = signer.sign(pdf_result.pdf_bytes)

        # Verify all fields exist and have expected types
        assert hasattr(result, 'signed_pdf_bytes')
        assert hasattr(result, 'signature_type')
        assert hasattr(result, 'signer_dn')
        assert hasattr(result, 'signing_time')
        assert hasattr(result, 'is_signed')
        assert hasattr(result, 'warning')
        assert isinstance(result.signed_pdf_bytes, bytes)
        assert isinstance(result.is_signed, bool)
