"""
Sprint 6 — XBRL Generator Tests

Tests XBRLGenerator (XBRL 2.1) and IXBRLGenerator (iXBRL / Inline XBRL).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/reporting-service'))

from datetime import date
from lxml import etree

from src.models import FinancialFact, ReportEntity, ReportRequest
from src.xbrl_generator import XBRLGenerator, IXBRLGenerator, _context_id

# ---------------------------------------------------------------------------
# Namespace constants (mirror what the generator uses)
# ---------------------------------------------------------------------------
NS_XBRL = "http://www.xbrl.org/2003/instance"
NS_LINK = "http://www.xbrl.org/2003/linkbase"
NS_ISO4217 = "http://www.xbrl.org/2003/iso4217"
NS_XHTML = "http://www.w3.org/1999/xhtml"
NS_IX = "http://www.xbrl.org/2013/inlineXBRL"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def make_entity():
    return ReportEntity(
        entity_id='test-entity-001',
        entity_name='Test Corp',
        country='US',
        currency='USD',
        fiscal_year_end='12-31',
        tax_id='12-3456789',
    )


def make_fact(account_code='1000', amount=10000.0, gifi_code='1000',
              xbrl_concept='us-gaap:CashAndCashEquivalentsAtCarryingValue'):
    return FinancialFact(
        account_code=account_code,
        account_name='Cash',
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
        amount=amount,
        currency='USD',
        debit_credit='D',
        entity_id='test-entity-001',
        gifi_code=gifi_code,
        xbrl_concept=xbrl_concept,
    )


def make_balanced_facts():
    """Two facts that are debits and credits of equal value."""
    debit = make_fact('1000', 5000.0, '1000', 'us-gaap:CashAndCashEquivalentsAtCarryingValue')
    credit = FinancialFact(
        account_code='2000',
        account_name='Accounts Payable',
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
        amount=5000.0,
        currency='USD',
        debit_credit='C',
        entity_id='test-entity-001',
    )
    return [debit, credit]


def make_request(facts=None):
    entity = make_entity()
    if facts is None:
        facts = [make_fact()]
    return ReportRequest(
        tenant_id='tenant-abc',
        entity=entity,
        framework='tax',
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
        facts=facts,
        report_title='Q1 2026 XBRL Report',
    )


# ---------------------------------------------------------------------------
# XBRLGenerator tests
# ---------------------------------------------------------------------------

class TestXBRLGenerator:

    def test_generate_returns_bytes(self):
        gen = XBRLGenerator()
        result = gen.generate(make_request())
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_root_namespace_is_xbrl_2_1(self):
        gen = XBRLGenerator()
        xml_bytes = gen.generate(make_request())
        root = etree.fromstring(xml_bytes)
        assert root.nsmap.get(None) == NS_XBRL or NS_XBRL in root.nsmap.values(), (
            f"Expected XBRL 2.1 namespace {NS_XBRL!r} in root nsmap, got: {root.nsmap}"
        )

    def test_root_tag_is_xbrl(self):
        gen = XBRLGenerator()
        xml_bytes = gen.generate(make_request())
        root = etree.fromstring(xml_bytes)
        assert root.tag == "{%s}xbrl" % NS_XBRL

    def test_context_element_present(self):
        gen = XBRLGenerator()
        xml_bytes = gen.generate(make_request())
        root = etree.fromstring(xml_bytes)
        contexts = root.findall("{%s}context" % NS_XBRL)
        assert len(contexts) >= 1, "Expected at least one xbrli:context element"

    def test_context_has_entity_and_period(self):
        gen = XBRLGenerator()
        xml_bytes = gen.generate(make_request())
        root = etree.fromstring(xml_bytes)
        ctx = root.find("{%s}context" % NS_XBRL)
        assert ctx is not None

        entity_elem = ctx.find("{%s}entity" % NS_XBRL)
        assert entity_elem is not None, "context must have entity child"

        period_elem = ctx.find("{%s}period" % NS_XBRL)
        assert period_elem is not None, "context must have period child"

        start = period_elem.find("{%s}startDate" % NS_XBRL)
        end = period_elem.find("{%s}endDate" % NS_XBRL)
        assert start is not None and start.text == '2026-01-01'
        assert end is not None and end.text == '2026-03-31'

    def test_unit_element_present_with_iso4217_measure(self):
        gen = XBRLGenerator()
        xml_bytes = gen.generate(make_request())
        root = etree.fromstring(xml_bytes)
        units = root.findall("{%s}unit" % NS_XBRL)
        assert len(units) >= 1, "Expected at least one xbrli:unit element"

        unit = units[0]
        measure = unit.find("{%s}measure" % NS_XBRL)
        assert measure is not None, "unit must contain a measure element"
        assert measure.text.startswith("iso4217:"), (
            f"measure text must use iso4217: prefix, got: {measure.text!r}"
        )

    def test_unit_measure_matches_currency(self):
        gen = XBRLGenerator()
        xml_bytes = gen.generate(make_request())
        root = etree.fromstring(xml_bytes)
        unit = root.find("{%s}unit" % NS_XBRL)
        measure = unit.find("{%s}measure" % NS_XBRL)
        assert measure.text == "iso4217:USD"

    def test_fact_element_has_decimals_2(self):
        gen = XBRLGenerator()
        xml_bytes = gen.generate(make_request())
        root = etree.fromstring(xml_bytes)
        # Facts are elements that carry contextRef + decimals
        facts_with_decimals = [
            elem for elem in root.iter()
            if elem.get('decimals') is not None
        ]
        assert len(facts_with_decimals) >= 1, "Expected at least one element with decimals attribute"
        for elem in facts_with_decimals:
            assert elem.get('decimals') == '2', (
                f"decimals must be '2', got {elem.get('decimals')!r} on <{elem.tag}>"
            )

    def test_fact_element_has_context_ref(self):
        gen = XBRLGenerator()
        xml_bytes = gen.generate(make_request())
        root = etree.fromstring(xml_bytes)
        fact_elems = [
            elem for elem in root.iter()
            if elem.get('contextRef') is not None
        ]
        assert len(fact_elems) >= 1

    def test_fact_amount_appears_as_numeric_string(self):
        fact = make_fact(amount=10000.0)
        gen = XBRLGenerator()
        xml_bytes = gen.generate(make_request([fact]))
        root = etree.fromstring(xml_bytes)
        fact_elems = [
            elem for elem in root.iter()
            if elem.get('decimals') == '2' and elem.text is not None
        ]
        assert len(fact_elems) >= 1
        # Verify the text is a numeric string
        val = float(fact_elems[0].text)
        assert val == 10000.0

    def test_context_id_is_deterministic(self):
        entity_id = 'test-entity-001'
        period_start = date(2026, 1, 1)
        period_end = date(2026, 3, 31)

        ctx1 = _context_id(entity_id, period_start, period_end)
        ctx2 = _context_id(entity_id, period_start, period_end)

        assert ctx1 == ctx2, "context ID must be identical for same inputs"

    def test_context_id_differs_for_different_periods(self):
        ctx_q1 = _context_id('ent-001', date(2026, 1, 1), date(2026, 3, 31))
        ctx_q2 = _context_id('ent-001', date(2026, 4, 1), date(2026, 6, 30))
        assert ctx_q1 != ctx_q2

    def test_context_id_starts_with_ctx_prefix(self):
        ctx = _context_id('ent-001', date(2026, 1, 1), date(2026, 3, 31))
        assert ctx.startswith('ctx_')

    def test_single_context_for_same_period_facts(self):
        """Multiple facts in the same period should produce only one context."""
        facts = [
            make_fact('1000', 1000.0),
            make_fact('1060', 2000.0),
            make_fact('1120', 3000.0),
        ]
        gen = XBRLGenerator()
        xml_bytes = gen.generate(make_request(facts))
        root = etree.fromstring(xml_bytes)
        contexts = root.findall("{%s}context" % NS_XBRL)
        assert len(contexts) == 1, (
            f"All facts in the same period should share one context, got {len(contexts)}"
        )

    def test_single_unit_for_same_currency_facts(self):
        """Multiple facts with the same currency should produce only one unit."""
        facts = [make_fact('1000', 1000.0), make_fact('1060', 2000.0)]
        gen = XBRLGenerator()
        xml_bytes = gen.generate(make_request(facts))
        root = etree.fromstring(xml_bytes)
        units = root.findall("{%s}unit" % NS_XBRL)
        assert len(units) == 1

    def test_balanced_journal_total_amounts(self):
        """Debit and credit facts of equal amounts should both appear in output."""
        facts = make_balanced_facts()
        gen = XBRLGenerator()
        xml_bytes = gen.generate(make_request(facts))
        root = etree.fromstring(xml_bytes)
        fact_elems = [
            elem for elem in root.iter()
            if elem.get('decimals') == '2' and elem.text is not None
        ]
        amounts = [float(e.text) for e in fact_elems]
        assert len(amounts) == 2
        assert abs(amounts[0] - 5000.0) < 0.01
        assert abs(amounts[1] - 5000.0) < 0.01

    def test_multiple_facts_ordered_by_account_code(self):
        """Facts should be emitted in account_code order."""
        facts = [
            make_fact('2000', 200.0),
            make_fact('1000', 100.0),
            make_fact('3000', 300.0),
        ]
        gen = XBRLGenerator()
        xml_bytes = gen.generate(make_request(facts))
        root = etree.fromstring(xml_bytes)
        fact_elems = [
            elem for elem in root.iter()
            if elem.get('decimals') == '2' and elem.text is not None
        ]
        amounts = [float(e.text) for e in fact_elems]
        # Sorted by account_code: 1000->100, 2000->200, 3000->300
        assert amounts == [100.0, 200.0, 300.0]

    def test_schema_ref_element_present(self):
        gen = XBRLGenerator()
        xml_bytes = gen.generate(make_request())
        root = etree.fromstring(xml_bytes)
        schema_refs = root.findall("{%s}schemaRef" % NS_LINK)
        assert len(schema_refs) >= 1, "Expected a link:schemaRef element"

    def test_output_is_valid_xml(self):
        gen = XBRLGenerator()
        xml_bytes = gen.generate(make_request())
        # Should not raise
        root = etree.fromstring(xml_bytes)
        assert root is not None

    def test_xml_declaration_present(self):
        gen = XBRLGenerator()
        xml_bytes = gen.generate(make_request())
        assert xml_bytes.startswith(b'<?xml'), "Output should begin with XML declaration"


# ---------------------------------------------------------------------------
# IXBRLGenerator tests
# ---------------------------------------------------------------------------

class TestIXBRLGenerator:

    def test_generate_returns_bytes(self):
        gen = IXBRLGenerator()
        result = gen.generate(make_request())
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_root_is_html_element(self):
        gen = IXBRLGenerator()
        xml_bytes = gen.generate(make_request())
        root = etree.fromstring(xml_bytes)
        assert root.tag == "{%s}html" % NS_XHTML, (
            f"Root should be XHTML html element, got {root.tag!r}"
        )

    def test_ix_namespace_declared_on_root(self):
        gen = IXBRLGenerator()
        xml_bytes = gen.generate(make_request())
        root = etree.fromstring(xml_bytes)
        assert 'ix' in root.nsmap, "ix namespace must be declared"
        assert root.nsmap['ix'] == NS_IX

    def test_ix_header_present(self):
        gen = IXBRLGenerator()
        xml_bytes = gen.generate(make_request())
        root = etree.fromstring(xml_bytes)
        head = root.find("{%s}head" % NS_XHTML)
        assert head is not None, "html must have a head element"
        ix_header = head.find("{%s}header" % NS_IX)
        assert ix_header is not None, "head must contain ix:header"

    def test_ix_resources_present_in_header(self):
        gen = IXBRLGenerator()
        xml_bytes = gen.generate(make_request())
        root = etree.fromstring(xml_bytes)
        head = root.find("{%s}head" % NS_XHTML)
        ix_header = head.find("{%s}header" % NS_IX)
        ix_resources = ix_header.find("{%s}resources" % NS_IX)
        assert ix_resources is not None, "ix:header must contain ix:resources"

    def test_ix_nonfraction_elements_present(self):
        gen = IXBRLGenerator()
        xml_bytes = gen.generate(make_request())
        root = etree.fromstring(xml_bytes)
        ix_facts = root.findall(".//{%s}nonFraction" % NS_IX)
        assert len(ix_facts) >= 1, "Expected at least one ix:nonFraction element"

    def test_ix_nonfraction_has_required_attributes(self):
        gen = IXBRLGenerator()
        xml_bytes = gen.generate(make_request())
        root = etree.fromstring(xml_bytes)
        ix_facts = root.findall(".//{%s}nonFraction" % NS_IX)
        for elem in ix_facts:
            assert elem.get('contextRef') is not None, "ix:nonFraction must have contextRef"
            assert elem.get('unitRef') is not None, "ix:nonFraction must have unitRef"
            assert elem.get('decimals') == '2', "ix:nonFraction must have decimals='2'"
            assert elem.get('name') is not None, "ix:nonFraction must have name"

    def test_ix_nonfraction_amount_is_numeric(self):
        fact = make_fact(amount=99999.42)
        gen = IXBRLGenerator()
        xml_bytes = gen.generate(make_request([fact]))
        root = etree.fromstring(xml_bytes)
        ix_facts = root.findall(".//{%s}nonFraction" % NS_IX)
        assert len(ix_facts) >= 1
        val = float(ix_facts[0].text)
        assert abs(val - 99999.42) < 0.001

    def test_context_in_ix_resources(self):
        """Contexts should be inside ix:resources, not in the body."""
        gen = IXBRLGenerator()
        xml_bytes = gen.generate(make_request())
        root = etree.fromstring(xml_bytes)
        head = root.find("{%s}head" % NS_XHTML)
        ix_header = head.find("{%s}header" % NS_IX)
        ix_resources = ix_header.find("{%s}resources" % NS_IX)

        XBRLI = "http://www.xbrl.org/2003/instance"
        contexts = ix_resources.findall("{%s}context" % XBRLI)
        assert len(contexts) >= 1, "ix:resources should contain xbrli:context elements"

    def test_unit_in_ix_resources(self):
        gen = IXBRLGenerator()
        xml_bytes = gen.generate(make_request())
        root = etree.fromstring(xml_bytes)
        head = root.find("{%s}head" % NS_XHTML)
        ix_header = head.find("{%s}header" % NS_IX)
        ix_resources = ix_header.find("{%s}resources" % NS_IX)

        XBRLI = "http://www.xbrl.org/2003/instance"
        units = ix_resources.findall("{%s}unit" % XBRLI)
        assert len(units) >= 1

    def test_body_present(self):
        gen = IXBRLGenerator()
        xml_bytes = gen.generate(make_request())
        root = etree.fromstring(xml_bytes)
        body = root.find("{%s}body" % NS_XHTML)
        assert body is not None, "html must have a body element"

    def test_output_is_valid_xml(self):
        gen = IXBRLGenerator()
        xml_bytes = gen.generate(make_request())
        root = etree.fromstring(xml_bytes)
        assert root is not None

    def test_context_id_consistent_between_xbrl_and_ixbrl(self):
        """The context ID helper produces the same ID for both generators."""
        entity_id = 'test-entity-001'
        period_start = date(2026, 1, 1)
        period_end = date(2026, 3, 31)

        ctx_id = _context_id(entity_id, period_start, period_end)

        # Check in XBRL
        xbrl_gen = XBRLGenerator()
        xml_bytes = xbrl_gen.generate(make_request())
        root = etree.fromstring(xml_bytes)
        ctx_elem = root.find("{%s}context" % NS_XBRL)
        assert ctx_elem.get('id') == ctx_id

        # Check in iXBRL
        ixbrl_gen = IXBRLGenerator()
        html_bytes = ixbrl_gen.generate(make_request())
        html_root = etree.fromstring(html_bytes)
        head = html_root.find("{%s}head" % NS_XHTML)
        ix_header = head.find("{%s}header" % NS_IX)
        ix_resources = ix_header.find("{%s}resources" % NS_IX)
        XBRLI = "http://www.xbrl.org/2003/instance"
        ixbrl_ctx = ix_resources.find("{%s}context" % XBRLI)
        assert ixbrl_ctx.get('id') == ctx_id
