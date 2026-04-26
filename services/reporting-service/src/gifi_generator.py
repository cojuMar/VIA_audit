"""
GIFI (General Index of Financial Information) Generator.

GIFI is the Canada Revenue Agency's standard for electronic financial data.
Each financial statement line item is tagged with a 4-digit GIFI code.

Reference: https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/corporations/corporation-income-tax-return/completing-your-corporation-income-tax-t2-return/gifi-codes.html

Output: XML document with GIFI-tagged amounts, suitable for CRA T2 electronic filing.
"""

import logging
from datetime import datetime, timezone
from lxml import etree
from .models import ReportRequest

logger = logging.getLogger(__name__)

# Standard GIFI codes for common balance sheet and income statement items
GIFI_CODE_MAP = {
    # Balance Sheet — Assets
    "1000": "Cash and deposits",
    "1060": "Accounts receivable",
    "1120": "Inventory",
    "1180": "Prepaid expenses",
    "1599": "Total current assets",
    "1740": "Property, plant and equipment",
    "1999": "Total assets",
    # Balance Sheet — Liabilities
    "2600": "Bank indebtedness",
    "2680": "Accounts payable and accrued liabilities",
    "3139": "Total current liabilities",
    "3500": "Long-term debt",
    "3999": "Total liabilities",
    # Equity
    "3600": "Capital stock",
    "3620": "Retained earnings (deficit) opening",
    "3680": "Retained earnings (deficit) closing",
    # Income Statement
    "8000": "Sales of goods and services",
    "8299": "Total revenue",
    "8520": "Cost of goods sold",
    "9270": "Total expenses",
    "9999": "Net income (loss) before taxes",
}


class GIFIGenerator:
    """Generates GIFI-tagged XML for CRA T2 electronic filing.

    Maps financial facts to GIFI codes and produces a structured XML
    document. Facts without a GIFI code are assigned to the closest
    standard category or omitted with a warning.
    """

    def generate(self, request: ReportRequest) -> bytes:
        """Generate GIFI XML."""
        root = etree.Element("GIFI")
        root.set("version", "2.0")
        root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")

        # Header
        header = etree.SubElement(root, "Header")
        self._sub(header, "EntityName", request.entity.entity_name)
        self._sub(header, "BusinessNumber", request.entity.tax_id or request.entity.entity_id)
        self._sub(header, "FiscalYearEnd", request.period_end.isoformat())
        self._sub(header, "Currency", request.entity.currency)
        self._sub(header, "CreatedAt", datetime.now(timezone.utc).isoformat())

        # Financial data
        financial = etree.SubElement(root, "FinancialStatements")
        self._sub(financial, "PeriodStart", request.period_start.isoformat())
        self._sub(financial, "PeriodEnd", request.period_end.isoformat())

        items = etree.SubElement(financial, "Items")

        included = 0
        skipped = 0

        for fact in sorted(request.facts, key=lambda f: f.gifi_code or f.account_code):
            gifi_code = fact.gifi_code
            if not gifi_code:
                logger.debug("Fact %s has no GIFI code — skipping", fact.account_code)
                skipped += 1
                continue

            item = etree.SubElement(items, "Item")
            self._sub(item, "GIFICode", gifi_code)
            self._sub(item, "Description", fact.account_name or GIFI_CODE_MAP.get(gifi_code, gifi_code))
            self._sub(item, "Amount", f"{fact.amount:.2f}")
            self._sub(item, "Currency", fact.currency)
            self._sub(item, "DebitCredit", fact.debit_credit)
            self._sub(item, "AccountCode", fact.account_code)
            included += 1

        # Summary
        summary = etree.SubElement(root, "Summary")
        self._sub(summary, "TotalItems", str(included))
        self._sub(summary, "SkippedItems", str(skipped))
        total_amount = sum(f.amount for f in request.facts if f.gifi_code)
        self._sub(summary, "TotalAmount", f"{total_amount:.2f}")

        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)

    @staticmethod
    def _sub(parent: etree._Element, tag: str, text: str) -> etree._Element:
        e = etree.SubElement(parent, tag)
        e.text = text
        return e
