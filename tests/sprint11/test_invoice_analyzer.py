import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/monitoring-service"))

from unittest.mock import MagicMock

from src.invoice_analyzer import InvoiceAnalyzer
from src.models import InvoiceRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_settings():
    s = MagicMock()
    s.invoice_fuzzy_amount_tolerance_pct = 1.0
    s.invoice_fuzzy_date_window_days = 7
    s.invoice_split_window_days = 30
    return s


def make_invoice(inv_id, vendor, amount, date, description=None, threshold=None):
    return InvoiceRecord(
        invoice_id=inv_id,
        vendor_name=vendor,
        amount=amount,
        invoice_date=date,
        description=description,
        approval_threshold=threshold,
    )


# ---------------------------------------------------------------------------
# TestInvoiceAnalyzer
# ---------------------------------------------------------------------------

class TestInvoiceAnalyzer:

    def test_exact_duplicate_same_vendor_amount_date(self):
        """Two invoices with identical vendor+amount on same date → 1 exact duplicate finding."""
        analyzer = InvoiceAnalyzer(make_settings())
        invoices = [
            make_invoice("INV001", "Acme Corp", 10000.0, "2024-01-15"),
            make_invoice("INV002", "Acme Corp", 10000.0, "2024-01-15"),
        ]
        findings = analyzer._detect_exact_duplicates(invoices)
        assert len(findings) == 1
        assert findings[0].finding_type == "duplicate_invoice"

    def test_exact_duplicate_different_vendors_no_match(self):
        """Same amount, different vendors → no exact duplicate."""
        analyzer = InvoiceAnalyzer(make_settings())
        invoices = [
            make_invoice("INV001", "Acme Corp", 10000.0, "2024-01-15"),
            make_invoice("INV002", "Beta LLC", 10000.0, "2024-01-15"),
        ]
        findings = analyzer._detect_exact_duplicates(invoices)
        assert len(findings) == 0

    def test_exact_duplicate_evidence_has_both_ids(self):
        """Finding evidence has both invoice IDs."""
        analyzer = InvoiceAnalyzer(make_settings())
        invoices = [
            make_invoice("INV001", "Acme Corp", 10000.0, "2024-01-15"),
            make_invoice("INV002", "Acme Corp", 10000.0, "2024-01-15"),
        ]
        findings = analyzer._detect_exact_duplicates(invoices)
        assert findings, "Expected at least one finding"
        evidence = findings[0].evidence
        inv_ids_in_evidence = {evidence.get("invoice_id_1"), evidence.get("invoice_id_2")}
        assert "INV001" in inv_ids_in_evidence, "INV001 must appear in evidence"
        assert "INV002" in inv_ids_in_evidence, "INV002 must appear in evidence"

    def test_fuzzy_duplicate_detects_similar_vendor_name(self):
        """'Acme Corp' and 'ACME CORP' same amount ±0.5% → fuzzy duplicate."""
        analyzer = InvoiceAnalyzer(make_settings())
        invoices = [
            make_invoice("INV001", "Acme Corp", 10000.0, "2024-01-15"),
            make_invoice("INV002", "ACME CORP", 10050.0, "2024-01-16"),  # 0.5% diff, 1 day apart
        ]
        findings = analyzer._detect_fuzzy_duplicates(invoices)
        assert len(findings) >= 1
        assert findings[0].finding_type == "near_duplicate_invoice"

    def test_fuzzy_duplicate_amount_outside_tolerance_no_match(self):
        """Amounts differ by 5% → no fuzzy match (tolerance is 1%)."""
        analyzer = InvoiceAnalyzer(make_settings())
        invoices = [
            make_invoice("INV001", "Acme Corp", 10000.0, "2024-01-15"),
            make_invoice("INV002", "ACME CORP", 10500.0, "2024-01-16"),  # 5% diff
        ]
        findings = analyzer._detect_fuzzy_duplicates(invoices)
        assert len(findings) == 0

    def test_fuzzy_duplicate_date_outside_window_no_match(self):
        """Same vendor+amount but 30 days apart → no match (window=7)."""
        analyzer = InvoiceAnalyzer(make_settings())
        invoices = [
            make_invoice("INV001", "Acme Corp", 10000.0, "2024-01-01"),
            make_invoice("INV002", "ACME CORP", 10000.0, "2024-01-31"),  # 30 days apart
        ]
        findings = analyzer._detect_fuzzy_duplicates(invoices)
        assert len(findings) == 0

    def test_invoice_split_detects_threshold_avoidance(self):
        """3 invoices to same vendor, each $4,900 (below $5,000 threshold) in 30 days → split finding."""
        analyzer = InvoiceAnalyzer(make_settings())
        invoices = [
            make_invoice("INV001", "Vendor X", 4900.0, "2024-01-05", threshold=5000.0),
            make_invoice("INV002", "Vendor X", 4900.0, "2024-01-12", threshold=5000.0),
            make_invoice("INV003", "Vendor X", 4900.0, "2024-01-19", threshold=5000.0),
        ]
        findings = analyzer._detect_invoice_splitting(invoices)
        assert len(findings) >= 1
        assert findings[0].finding_type == "invoice_splitting"

    def test_invoice_split_no_threshold_no_finding(self):
        """Same invoices but no approval_threshold set → no split finding."""
        analyzer = InvoiceAnalyzer(make_settings())
        invoices = [
            make_invoice("INV001", "Vendor X", 4900.0, "2024-01-05", threshold=None),
            make_invoice("INV002", "Vendor X", 4900.0, "2024-01-12", threshold=None),
            make_invoice("INV003", "Vendor X", 4900.0, "2024-01-19", threshold=None),
        ]
        findings = analyzer._detect_invoice_splitting(invoices)
        assert len(findings) == 0

    def test_round_amount_flags_exact_thousand(self):
        """Invoice for $5,000.00 above $1000 → round amount finding."""
        analyzer = InvoiceAnalyzer(make_settings())
        invoices = [
            make_invoice("INV001", "Vendor Y", 5000.0, "2024-01-15"),
        ]
        findings = analyzer._detect_round_amounts(invoices)
        assert len(findings) >= 1
        assert findings[0].finding_type == "round_amount_invoice"

    def test_round_amount_skips_small_amounts(self):
        """$100.00 → no finding (below $1000 threshold)."""
        analyzer = InvoiceAnalyzer(make_settings())
        invoices = [
            make_invoice("INV001", "Vendor Y", 100.0, "2024-01-15"),
        ]
        findings = analyzer._detect_round_amounts(invoices)
        assert len(findings) == 0

    def test_empty_invoices_returns_empty(self):
        """[] → []."""
        analyzer = InvoiceAnalyzer(make_settings())
        findings = analyzer.analyze([])
        assert findings == []

    def test_analyze_combines_all_checks(self):
        """Call analyze() returns findings from all 4 detectors."""
        analyzer = InvoiceAnalyzer(make_settings())

        invoices = [
            # Exact duplicate pair
            make_invoice("INV001", "Exact Vendor", 10000.0, "2024-01-15"),
            make_invoice("INV002", "Exact Vendor", 10000.0, "2024-01-15"),
            # Fuzzy duplicate pair
            make_invoice("INV003", "Fuzzy Corp", 20000.0, "2024-02-01"),
            make_invoice("INV004", "FUZZY CORP", 20100.0, "2024-02-02"),
            # Invoice split cluster
            make_invoice("INV005", "Split Vendor", 4900.0, "2024-03-01", threshold=5000.0),
            make_invoice("INV006", "Split Vendor", 4900.0, "2024-03-08", threshold=5000.0),
            make_invoice("INV007", "Split Vendor", 4900.0, "2024-03-15", threshold=5000.0),
            # Round amount
            make_invoice("INV008", "Round Vendor", 50000.0, "2024-04-01"),
        ]

        findings = analyzer.analyze(invoices)
        types_found = {f.finding_type for f in findings}

        assert "duplicate_invoice" in types_found, "Expected exact duplicate finding"
        assert "near_duplicate_invoice" in types_found, "Expected fuzzy duplicate finding"
        assert "invoice_splitting" in types_found, "Expected invoice split finding"
        assert "round_amount_invoice" in types_found, "Expected round amount finding"
