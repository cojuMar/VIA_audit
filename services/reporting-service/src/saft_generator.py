"""
SAF-T (Standard Audit File for Tax) Generator.

Produces XML conforming to the OECD SAF-T Financial (version 2.0) schema.
Reference: https://www.oecd.org/tax/forum-on-tax-administration/publications-and-products/standard-audit-file-for-tax.htm

SAF-T structure:
  <AuditFile>
    <Header>          — Company info, fiscal year, software info
    <MasterFiles>     — Chart of accounts, customers, suppliers, tax codes
    <GeneralLedger>   — Journal entries with debit/credit lines
  </AuditFile>

Design: Uses lxml for safe XML generation (no string templates).
Amounts use 2 decimal places, always in the entity's default currency.
"""

import logging
from datetime import date, datetime, timezone
from typing import List
from lxml import etree
from .models import FinancialFact, JournalEntry, ReportEntity, ReportRequest

logger = logging.getLogger(__name__)

# SAF-T OECD namespace
NS_SAFT = "urn:StandardAuditFile-Taxation-Financial:NO"  # Norwegian SAF-T (most widely adopted)
SAFT_VERSION = "1.10"

SOFTWARE_INFO = {
    "SoftwareCompanyName": "Aegis Compliance Platform",
    "SoftwareID": "aegis-reporting-service",
    "SoftwareVersion": "2.0.0",
}


def _fmt_date(d: date) -> str:
    return d.isoformat()


def _fmt_amount(amount: float) -> str:
    return f"{amount:.2f}"


class SAFTGenerator:
    """Generates SAF-T XML from a ReportRequest.

    The generator produces a complete SAF-T Financial file including:
    - Header with entity metadata and software information
    - MasterFiles with chart of accounts derived from financial facts
    - GeneralLedger with all journal entries

    Note: SAF-T does not include financial amounts directly in MasterFiles;
    only account definitions. Amounts appear exclusively in journal entries.
    """

    def generate(self, request: ReportRequest) -> bytes:
        """Generate SAF-T XML bytes."""
        nsmap = {None: NS_SAFT}
        root = etree.Element("{%s}AuditFile" % NS_SAFT, nsmap=nsmap)

        self._add_header(root, request)
        self._add_master_files(root, request)
        self._add_general_ledger(root, request)

        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)

    def _add_header(self, root: etree._Element, request: ReportRequest) -> None:
        header = etree.SubElement(root, "{%s}Header" % NS_SAFT)

        def _sub(parent, tag, text):
            e = etree.SubElement(parent, "{%s}%s" % (NS_SAFT, tag))
            e.text = str(text)
            return e

        _sub(header, "AuditFileVersion", SAFT_VERSION)
        _sub(header, "AuditFileCountry", request.entity.country)
        _sub(header, "AuditFileDateCreated", datetime.now(timezone.utc).date().isoformat())
        _sub(header, "SoftwareCompanyName", SOFTWARE_INFO["SoftwareCompanyName"])
        _sub(header, "SoftwareID", SOFTWARE_INFO["SoftwareID"])
        _sub(header, "SoftwareVersion", SOFTWARE_INFO["SoftwareVersion"])

        company = etree.SubElement(header, "{%s}Company" % NS_SAFT)
        _sub(company, "RegistrationNumber", request.entity.registration_number or request.entity.entity_id)
        _sub(company, "Name", request.entity.entity_name)
        if request.entity.tax_id:
            _sub(company, "TaxRegistrationNumber", request.entity.tax_id)

        _sub(header, "DefaultCurrencyCode", request.entity.currency)

        selection = etree.SubElement(header, "{%s}SelectionCriteria" % NS_SAFT)
        _sub(selection, "SelectionStartDate", _fmt_date(request.period_start))
        _sub(selection, "SelectionEndDate", _fmt_date(request.period_end))

    def _add_master_files(self, root: etree._Element, request: ReportRequest) -> None:
        master = etree.SubElement(root, "{%s}MasterFiles" % NS_SAFT)

        # Build unique accounts from facts
        accounts_seen = {}
        for fact in request.facts:
            if fact.account_code not in accounts_seen:
                accounts_seen[fact.account_code] = fact

        if accounts_seen:
            accounts_elem = etree.SubElement(master, "{%s}GeneralLedgerAccounts" % NS_SAFT)
            for code, fact in sorted(accounts_seen.items()):
                acct = etree.SubElement(accounts_elem, "{%s}Account" % NS_SAFT)
                self._sub(acct, "AccountID", code)
                self._sub(acct, "AccountDescription", fact.account_name)
                self._sub(acct, "StandardAccountID", code)
                self._sub(acct, "AccountType", "GL")

    def _add_general_ledger(self, root: etree._Element, request: ReportRequest) -> None:
        gl = etree.SubElement(root, "{%s}GeneralLedger" % NS_SAFT)

        self._sub(gl, "NumberOfEntries", str(len(request.journal_entries)))

        total_debit = sum(
            line.amount for je in request.journal_entries
            for line in je.lines if line.debit_credit == 'D'
        )
        total_credit = sum(
            line.amount for je in request.journal_entries
            for line in je.lines if line.debit_credit == 'C'
        )
        self._sub(gl, "TotalDebit", _fmt_amount(total_debit))
        self._sub(gl, "TotalCredit", _fmt_amount(total_credit))

        for je in request.journal_entries:
            entry = etree.SubElement(gl, "{%s}Journal" % NS_SAFT)
            self._sub(entry, "JournalID", je.entry_id)
            self._sub(entry, "Description", je.description)
            self._sub(entry, "TransactionDate", _fmt_date(je.entry_date))

            for i, line in enumerate(je.lines):
                line_elem = etree.SubElement(entry, "{%s}Transaction" % NS_SAFT)
                self._sub(line_elem, "TransactionID", f"{je.entry_id}-{i+1:04d}")
                self._sub(line_elem, "AccountID", line.account_code)
                self._sub(line_elem, "Description", line.description or je.description)
                self._sub(line_elem, "Amount", _fmt_amount(line.amount))
                self._sub(line_elem, "AmountCurrencyCode", line.currency)
                self._sub(line_elem, "DebitCreditIndicator", line.debit_credit)

    @staticmethod
    def _sub(parent: etree._Element, tag: str, text: str) -> etree._Element:
        e = etree.SubElement(parent, "{%s}%s" % (NS_SAFT, tag))
        e.text = text
        return e
