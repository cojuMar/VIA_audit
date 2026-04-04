"""
Report generation data models.

ReportRequest is the primary input to all generators. It carries:
- Tenant and period metadata
- Evidence records (canonical payloads from evidence_records table)
- Audit narratives (from audit_narratives table)
- Financial facts (mapped from evidence/ledger records for XBRL/SAF-T)
"""

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Dict, Any


@dataclass
class FinancialFact:
    """A single financial fact for XBRL/SAF-T/GIFI output."""
    account_code: str       # Chart of accounts code
    account_name: str
    period_start: date
    period_end: date
    amount: float           # Always positive; debit/credit indicated by debit_credit
    currency: str           # ISO 4217 (e.g. 'USD', 'EUR', 'CAD')
    debit_credit: str       # 'D' or 'C'
    entity_id: str          # Source evidence record ID
    description: Optional[str] = None
    gifi_code: Optional[str] = None    # CRA GIFI code if applicable
    xbrl_concept: Optional[str] = None # XBRL concept name (e.g. 'us-gaap:Assets')


@dataclass
class JournalEntry:
    """A double-entry journal entry for SAF-T output."""
    entry_id: str
    entry_date: date
    description: str
    lines: List[FinancialFact]

    def is_balanced(self) -> bool:
        """Double-entry: debits must equal credits."""
        debits = sum(f.amount for f in self.lines if f.debit_credit == 'D')
        credits = sum(f.amount for f in self.lines if f.debit_credit == 'C')
        return abs(debits - credits) < 0.01


@dataclass
class ReportEntity:
    """The reporting entity (company/organization)."""
    entity_id: str        # Tax ID / registration number
    entity_name: str
    country: str          # ISO 3166-1 alpha-2
    currency: str         # ISO 4217 default currency
    fiscal_year_end: str  # MM-DD (e.g. '12-31')
    tax_id: Optional[str] = None
    registration_number: Optional[str] = None


@dataclass
class ReportRequest:
    """Complete input for any report format."""
    tenant_id: str
    entity: ReportEntity
    framework: str          # 'soc2', 'iso27001', 'pci_dss', 'tax', 'custom'
    period_start: date
    period_end: date
    facts: List[FinancialFact] = field(default_factory=list)
    journal_entries: List[JournalEntry] = field(default_factory=list)
    narratives: List[Dict[str, Any]] = field(default_factory=list)  # audit_narratives rows
    evidence_records: List[Dict[str, Any]] = field(default_factory=list)
    taxonomy_namespace: str = "http://www.xbrl.org/2003/instance"
    report_title: Optional[str] = None
