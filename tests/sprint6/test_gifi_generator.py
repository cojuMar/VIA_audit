"""
Sprint 6 — GIFI Generator Tests

Tests GIFIGenerator output:
  - Facts with valid GIFI codes are included
  - Facts without GIFI codes are skipped (SkippedItems count)
  - Amounts summed correctly per GIFI code
  - Output XML contains TotalItems and TotalAmount in Summary
  - Mix of GIFI-coded and non-coded facts handled correctly
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/reporting-service'))

from datetime import date
from lxml import etree

from src.models import FinancialFact, ReportEntity, ReportRequest
from src.gifi_generator import GIFIGenerator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_entity():
    return ReportEntity(
        entity_id='test-entity-001',
        entity_name='Test Corp',
        country='CA',
        currency='CAD',
        fiscal_year_end='12-31',
        tax_id='12-3456789',
    )


def make_fact(account_code='1000', amount=10000.0, gifi_code='1000',
              debit_credit='D', currency='CAD'):
    return FinancialFact(
        account_code=account_code,
        account_name='Cash',
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        amount=amount,
        currency=currency,
        debit_credit=debit_credit,
        entity_id='test-entity-001',
        gifi_code=gifi_code,
    )


def make_fact_no_gifi(account_code='9999', amount=500.0):
    return FinancialFact(
        account_code=account_code,
        account_name='Uncategorized',
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        amount=amount,
        currency='CAD',
        debit_credit='D',
        entity_id='test-entity-001',
        gifi_code=None,
    )


def make_request(facts):
    return ReportRequest(
        tenant_id='tenant-abc',
        entity=make_entity(),
        framework='tax',
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        facts=facts,
    )


def parse_xml(xml_bytes: bytes) -> etree._Element:
    return etree.fromstring(xml_bytes)


def find_text(root: etree._Element, xpath: str) -> str:
    elem = root.find(xpath)
    assert elem is not None, f"Element not found: {xpath}"
    return elem.text


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGIFIGenerator:

    def test_generate_returns_bytes(self):
        gen = GIFIGenerator()
        result = gen.generate(make_request([make_fact()]))
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_output_is_valid_xml(self):
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request([make_fact()]))
        root = parse_xml(xml_bytes)
        assert root is not None

    def test_xml_declaration_present(self):
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request([make_fact()]))
        assert xml_bytes.startswith(b'<?xml')

    def test_root_element_is_gifi(self):
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request([make_fact()]))
        root = parse_xml(xml_bytes)
        assert root.tag == 'GIFI'

    def test_root_has_version_attribute(self):
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request([make_fact()]))
        root = parse_xml(xml_bytes)
        assert root.get('version') == '2.0'

    def test_fact_with_gifi_code_is_included(self):
        fact = make_fact('1000', 10000.0, '1000')
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request([fact]))
        root = parse_xml(xml_bytes)
        items = root.findall('.//Items/Item')
        assert len(items) == 1, f"Expected 1 item, got {len(items)}"
        gifi_code_elem = items[0].find('GIFICode')
        assert gifi_code_elem is not None
        assert gifi_code_elem.text == '1000'

    def test_fact_without_gifi_code_is_skipped(self):
        fact_with = make_fact('1000', 10000.0, '1000')
        fact_without = make_fact_no_gifi('9999', 500.0)
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request([fact_with, fact_without]))
        root = parse_xml(xml_bytes)
        items = root.findall('.//Items/Item')
        # Only the fact with a GIFI code should appear
        assert len(items) == 1
        gifi_code_elem = items[0].find('GIFICode')
        assert gifi_code_elem.text == '1000'

    def test_skipped_items_count_when_no_gifi(self):
        fact_without = make_fact_no_gifi('9999', 500.0)
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request([fact_without]))
        root = parse_xml(xml_bytes)
        skipped = find_text(root, './/Summary/SkippedItems')
        assert skipped == '1', f"Expected SkippedItems=1, got {skipped!r}"

    def test_skipped_items_count_with_mixed_facts(self):
        facts = [
            make_fact('1000', 10000.0, '1000'),
            make_fact_no_gifi('9999', 500.0),
            make_fact_no_gifi('8888', 300.0),
        ]
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request(facts))
        root = parse_xml(xml_bytes)
        skipped = find_text(root, './/Summary/SkippedItems')
        assert skipped == '2'

    def test_total_items_count_reflects_included_facts(self):
        facts = [
            make_fact('1000', 1000.0, '1000'),
            make_fact('1060', 2000.0, '1060'),
            make_fact('1120', 3000.0, '1120'),
            make_fact_no_gifi('9999', 500.0),
        ]
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request(facts))
        root = parse_xml(xml_bytes)
        total_items = find_text(root, './/Summary/TotalItems')
        assert total_items == '3', f"Expected TotalItems=3, got {total_items!r}"

    def test_total_amount_is_sum_of_gifi_facts(self):
        facts = [
            make_fact('1000', 1000.0, '1000'),
            make_fact('1060', 2000.0, '1060'),
            make_fact_no_gifi('9999', 500.0),  # should not be counted
        ]
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request(facts))
        root = parse_xml(xml_bytes)
        total_amount_str = find_text(root, './/Summary/TotalAmount')
        total_amount = float(total_amount_str)
        assert abs(total_amount - 3000.0) < 0.01, (
            f"Expected TotalAmount=3000.00, got {total_amount}"
        )

    def test_total_amount_excludes_non_gifi_facts(self):
        facts = [
            make_fact('1000', 5000.0, '1000'),
            make_fact_no_gifi('9999', 99999.0),  # large amount, must be excluded
        ]
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request(facts))
        root = parse_xml(xml_bytes)
        total_amount = float(find_text(root, './/Summary/TotalAmount'))
        assert abs(total_amount - 5000.0) < 0.01, (
            f"Non-GIFI fact amount should not appear in TotalAmount, got {total_amount}"
        )

    def test_item_amount_formatted_to_2_decimals(self):
        fact = make_fact('1000', 12345.6789, '1000')
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request([fact]))
        root = parse_xml(xml_bytes)
        item = root.find('.//Items/Item')
        amount_text = item.find('Amount').text
        amount = float(amount_text)
        # Amount should be preserved as float-parseable
        assert abs(amount - 12345.68) < 0.01

    def test_item_has_required_fields(self):
        fact = make_fact('1000', 5000.0, '1000')
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request([fact]))
        root = parse_xml(xml_bytes)
        item = root.find('.//Items/Item')
        assert item.find('GIFICode') is not None
        assert item.find('Description') is not None
        assert item.find('Amount') is not None
        assert item.find('Currency') is not None
        assert item.find('DebitCredit') is not None
        assert item.find('AccountCode') is not None

    def test_item_account_code_matches_fact(self):
        fact = make_fact('1060', 2000.0, '1060')
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request([fact]))
        root = parse_xml(xml_bytes)
        item = root.find('.//Items/Item')
        assert item.find('AccountCode').text == '1060'

    def test_item_debit_credit_indicator_preserved(self):
        debit_fact = make_fact('1000', 5000.0, '1000', 'D')
        credit_fact = make_fact('2600', 5000.0, '2600', 'C')
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request([debit_fact, credit_fact]))
        root = parse_xml(xml_bytes)
        items = root.findall('.//Items/Item')
        dc_values = {item.find('GIFICode').text: item.find('DebitCredit').text for item in items}
        assert dc_values.get('1000') == 'D'
        assert dc_values.get('2600') == 'C'

    def test_header_entity_name_present(self):
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request([make_fact()]))
        root = parse_xml(xml_bytes)
        entity_name = find_text(root, './/Header/EntityName')
        assert entity_name == 'Test Corp'

    def test_header_fiscal_year_end_present(self):
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request([make_fact()]))
        root = parse_xml(xml_bytes)
        fiscal_year_end = find_text(root, './/Header/FiscalYearEnd')
        assert fiscal_year_end == '2026-12-31'

    def test_summary_present(self):
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request([make_fact()]))
        root = parse_xml(xml_bytes)
        summary = root.find('.//Summary')
        assert summary is not None, "GIFI XML must contain a Summary element"
        assert summary.find('TotalItems') is not None
        assert summary.find('SkippedItems') is not None
        assert summary.find('TotalAmount') is not None

    def test_all_facts_without_gifi_produces_zero_items(self):
        facts = [make_fact_no_gifi('9999', 100.0), make_fact_no_gifi('8888', 200.0)]
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request(facts))
        root = parse_xml(xml_bytes)
        total_items = find_text(root, './/Summary/TotalItems')
        skipped = find_text(root, './/Summary/SkippedItems')
        assert total_items == '0'
        assert skipped == '2'

    def test_empty_facts_list(self):
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request([]))
        root = parse_xml(xml_bytes)
        assert root is not None
        total_items = find_text(root, './/Summary/TotalItems')
        assert total_items == '0'

    def test_multiple_gifi_codes_all_appear(self):
        facts = [
            make_fact('1000', 1000.0, '1000'),
            make_fact('1060', 2000.0, '1060'),
            make_fact('8000', 5000.0, '8000'),
        ]
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request(facts))
        root = parse_xml(xml_bytes)
        items = root.findall('.//Items/Item')
        codes = {item.find('GIFICode').text for item in items}
        assert '1000' in codes
        assert '1060' in codes
        assert '8000' in codes

    def test_financial_statements_period_dates(self):
        gen = GIFIGenerator()
        xml_bytes = gen.generate(make_request([make_fact()]))
        root = parse_xml(xml_bytes)
        period_start = find_text(root, './/FinancialStatements/PeriodStart')
        period_end = find_text(root, './/FinancialStatements/PeriodEnd')
        assert period_start == '2026-01-01'
        assert period_end == '2026-12-31'
