"""
Sprint 6 — SAF-T Generator Tests

Tests SAFTGenerator output conformance:
  - Valid XML
  - Norwegian SAF-T namespace (urn:StandardAuditFile-Taxation-Financial:NO)
  - Header / Company structure
  - MasterFiles / GeneralLedgerAccounts
  - GeneralLedger with balanced debit/credit totals
  - SAFTVersion == '1.10'
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/reporting-service'))

from datetime import date
from lxml import etree

from src.models import FinancialFact, JournalEntry, ReportEntity, ReportRequest
from src.saft_generator import SAFTGenerator, NS_SAFT, SAFT_VERSION

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_entity():
    return ReportEntity(
        entity_id='test-entity-001',
        entity_name='Test Corp',
        country='US',
        currency='USD',
        fiscal_year_end='12-31',
        tax_id='12-3456789',
        registration_number='REG-001',
    )


def make_fact(account_code='1000', account_name='Cash', amount=5000.0, debit_credit='D'):
    return FinancialFact(
        account_code=account_code,
        account_name=account_name,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
        amount=amount,
        currency='USD',
        debit_credit=debit_credit,
        entity_id='test-entity-001',
    )


def make_balanced_journal_entry():
    """A balanced double-entry journal entry: debit 5000, credit 5000."""
    return JournalEntry(
        entry_id='je-test-001',
        entry_date=date(2026, 3, 31),
        description='Test balanced entry',
        lines=[
            make_fact('1000', 'Cash', 5000.0, 'D'),
            make_fact('2000', 'Accounts Payable', 5000.0, 'C'),
        ]
    )


def make_request(facts=None, journal_entries=None):
    if facts is None:
        facts = [make_fact('1000', 'Cash', 5000.0, 'D'),
                 make_fact('2000', 'Accounts Payable', 5000.0, 'C')]
    if journal_entries is None:
        journal_entries = [make_balanced_journal_entry()]
    return ReportRequest(
        tenant_id='tenant-abc',
        entity=make_entity(),
        framework='tax',
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
        facts=facts,
        journal_entries=journal_entries,
    )


def parse_xml(xml_bytes: bytes) -> etree._Element:
    return etree.fromstring(xml_bytes)


def ns(tag: str) -> str:
    """Qualify a tag with the SAF-T namespace."""
    return "{%s}%s" % (NS_SAFT, tag)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSAFTGenerator:

    def test_generate_returns_bytes(self):
        gen = SAFTGenerator()
        result = gen.generate(make_request())
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_output_is_valid_xml(self):
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request())
        root = parse_xml(xml_bytes)
        assert root is not None

    def test_xml_declaration_present(self):
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request())
        assert xml_bytes.startswith(b'<?xml')

    def test_root_element_is_audit_file(self):
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request())
        root = parse_xml(xml_bytes)
        assert root.tag == ns('AuditFile'), (
            f"Root element must be AuditFile in SAF-T namespace, got: {root.tag!r}"
        )

    def test_namespace_is_norwegian_saft(self):
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request())
        root = parse_xml(xml_bytes)
        # Default namespace should be the Norwegian SAF-T namespace
        ns_in_map = root.nsmap.get(None)
        assert ns_in_map == NS_SAFT, (
            f"Expected namespace {NS_SAFT!r}, got {ns_in_map!r}"
        )

    def test_header_present(self):
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request())
        root = parse_xml(xml_bytes)
        header = root.find(ns('Header'))
        assert header is not None, "AuditFile must contain a Header element"

    def test_saft_version_is_1_10(self):
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request())
        root = parse_xml(xml_bytes)
        header = root.find(ns('Header'))
        version_elem = header.find(ns('AuditFileVersion'))
        assert version_elem is not None, "Header must contain AuditFileVersion"
        assert version_elem.text == '1.10', (
            f"SAFTVersion must be '1.10', got {version_elem.text!r}"
        )

    def test_saft_version_constant_matches_output(self):
        """The SAFT_VERSION constant equals '1.10' and matches generated output."""
        assert SAFT_VERSION == '1.10'
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request())
        root = parse_xml(xml_bytes)
        header = root.find(ns('Header'))
        version_elem = header.find(ns('AuditFileVersion'))
        assert version_elem.text == SAFT_VERSION

    def test_header_contains_company(self):
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request())
        root = parse_xml(xml_bytes)
        header = root.find(ns('Header'))
        company = header.find(ns('Company'))
        assert company is not None, "Header must contain a Company element"

    def test_company_name_matches_entity(self):
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request())
        root = parse_xml(xml_bytes)
        header = root.find(ns('Header'))
        company = header.find(ns('Company'))
        name_elem = company.find(ns('Name'))
        assert name_elem is not None
        assert name_elem.text == 'Test Corp'

    def test_company_registration_number_present(self):
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request())
        root = parse_xml(xml_bytes)
        header = root.find(ns('Header'))
        company = header.find(ns('Company'))
        reg = company.find(ns('RegistrationNumber'))
        assert reg is not None
        # Should be the registration_number or entity_id fallback
        assert reg.text in ('REG-001', 'test-entity-001')

    def test_header_default_currency_code(self):
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request())
        root = parse_xml(xml_bytes)
        header = root.find(ns('Header'))
        currency_elem = header.find(ns('DefaultCurrencyCode'))
        assert currency_elem is not None
        assert currency_elem.text == 'USD'

    def test_master_files_present(self):
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request())
        root = parse_xml(xml_bytes)
        master = root.find(ns('MasterFiles'))
        assert master is not None, "AuditFile must contain MasterFiles"

    def test_general_ledger_accounts_present(self):
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request())
        root = parse_xml(xml_bytes)
        master = root.find(ns('MasterFiles'))
        accounts = master.find(ns('GeneralLedgerAccounts'))
        assert accounts is not None, "MasterFiles must contain GeneralLedgerAccounts"

    def test_general_ledger_accounts_contains_account_entries(self):
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request())
        root = parse_xml(xml_bytes)
        master = root.find(ns('MasterFiles'))
        accounts = master.find(ns('GeneralLedgerAccounts'))
        account_elems = accounts.findall(ns('Account'))
        assert len(account_elems) >= 1, "GeneralLedgerAccounts must contain at least one Account"

    def test_account_ids_match_facts(self):
        facts = [
            make_fact('1000', 'Cash', 1000.0, 'D'),
            make_fact('2000', 'AP', 1000.0, 'C'),
            make_fact('3000', 'Revenue', 2000.0, 'C'),
        ]
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request(facts=facts))
        root = parse_xml(xml_bytes)
        master = root.find(ns('MasterFiles'))
        accounts = master.find(ns('GeneralLedgerAccounts'))
        account_ids = {a.find(ns('AccountID')).text for a in accounts.findall(ns('Account'))}
        assert '1000' in account_ids
        assert '2000' in account_ids
        assert '3000' in account_ids

    def test_no_duplicate_account_entries(self):
        """Multiple facts with the same account_code should produce one Account entry."""
        facts = [
            make_fact('1000', 'Cash', 1000.0, 'D'),
            make_fact('1000', 'Cash', 500.0, 'D'),
        ]
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request(facts=facts))
        root = parse_xml(xml_bytes)
        master = root.find(ns('MasterFiles'))
        accounts = master.find(ns('GeneralLedgerAccounts'))
        account_elems = accounts.findall(ns('Account'))
        ids = [a.find(ns('AccountID')).text for a in account_elems]
        assert ids.count('1000') == 1, "Account 1000 should appear only once in MasterFiles"

    def test_general_ledger_section_present(self):
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request())
        root = parse_xml(xml_bytes)
        gl = root.find(ns('GeneralLedger'))
        assert gl is not None, "AuditFile must contain GeneralLedger"

    def test_general_ledger_has_journal_entries(self):
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request())
        root = parse_xml(xml_bytes)
        gl = root.find(ns('GeneralLedger'))
        journals = gl.findall(ns('Journal'))
        assert len(journals) >= 1, "GeneralLedger must contain at least one Journal entry"

    def test_total_debit_equals_total_credit_for_balanced_entries(self):
        """For balanced journal entries, TotalDebit must equal TotalCredit."""
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request())
        root = parse_xml(xml_bytes)
        gl = root.find(ns('GeneralLedger'))

        total_debit_elem = gl.find(ns('TotalDebit'))
        total_credit_elem = gl.find(ns('TotalCredit'))

        assert total_debit_elem is not None, "GeneralLedger must have TotalDebit"
        assert total_credit_elem is not None, "GeneralLedger must have TotalCredit"

        total_debit = float(total_debit_elem.text)
        total_credit = float(total_credit_elem.text)

        assert abs(total_debit - total_credit) < 0.01, (
            f"TotalDebit ({total_debit}) must equal TotalCredit ({total_credit}) "
            f"for balanced entries"
        )

    def test_total_debit_value_correct(self):
        """TotalDebit should equal sum of all debit lines across journal entries."""
        je = make_balanced_journal_entry()  # 5000 debit, 5000 credit
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request(journal_entries=[je]))
        root = parse_xml(xml_bytes)
        gl = root.find(ns('GeneralLedger'))
        total_debit = float(gl.find(ns('TotalDebit')).text)
        assert abs(total_debit - 5000.0) < 0.01

    def test_total_credit_value_correct(self):
        je = make_balanced_journal_entry()
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request(journal_entries=[je]))
        root = parse_xml(xml_bytes)
        gl = root.find(ns('GeneralLedger'))
        total_credit = float(gl.find(ns('TotalCredit')).text)
        assert abs(total_credit - 5000.0) < 0.01

    def test_number_of_entries_matches(self):
        entries = [make_balanced_journal_entry(), make_balanced_journal_entry()]
        entries[1] = JournalEntry(
            entry_id='je-test-002',
            entry_date=date(2026, 3, 31),
            description='Second entry',
            lines=[
                make_fact('1060', 'AR', 3000.0, 'D'),
                make_fact('8000', 'Revenue', 3000.0, 'C'),
            ]
        )
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request(journal_entries=entries))
        root = parse_xml(xml_bytes)
        gl = root.find(ns('GeneralLedger'))
        num_elem = gl.find(ns('NumberOfEntries'))
        assert num_elem is not None
        assert num_elem.text == '2'

    def test_journal_entry_has_transaction_lines(self):
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request())
        root = parse_xml(xml_bytes)
        gl = root.find(ns('GeneralLedger'))
        journal = gl.find(ns('Journal'))
        transactions = journal.findall(ns('Transaction'))
        assert len(transactions) == 2, "A journal entry with 2 lines should have 2 Transaction elements"

    def test_transaction_has_debit_credit_indicator(self):
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request())
        root = parse_xml(xml_bytes)
        gl = root.find(ns('GeneralLedger'))
        journal = gl.find(ns('Journal'))
        transactions = journal.findall(ns('Transaction'))
        indicators = {t.find(ns('DebitCreditIndicator')).text for t in transactions}
        assert 'D' in indicators
        assert 'C' in indicators

    def test_selection_criteria_dates_in_header(self):
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request())
        root = parse_xml(xml_bytes)
        header = root.find(ns('Header'))
        selection = header.find(ns('SelectionCriteria'))
        assert selection is not None
        start = selection.find(ns('SelectionStartDate'))
        end = selection.find(ns('SelectionEndDate'))
        assert start is not None and start.text == '2026-01-01'
        assert end is not None and end.text == '2026-03-31'

    def test_empty_journal_entries_still_valid(self):
        """Request with no journal entries should produce valid SAF-T with empty GL."""
        gen = SAFTGenerator()
        xml_bytes = gen.generate(make_request(facts=[], journal_entries=[]))
        root = parse_xml(xml_bytes)
        assert root is not None
        gl = root.find(ns('GeneralLedger'))
        assert gl is not None
        num_elem = gl.find(ns('NumberOfEntries'))
        assert num_elem.text == '0'
