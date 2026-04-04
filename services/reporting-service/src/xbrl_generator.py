"""
XBRL 2.1 and iXBRL (Inline XBRL) generator.

Produces standards-compliant XBRL instance documents and iXBRL reports
suitable for regulatory filing and auditor review.

XBRL 2.1 spec: https://www.xbrl.org/Specification/XBRL-2.1/REC-2003-12-31/
iXBRL spec:    https://www.xbrl.org/specification/inlinexbrl-part1/rec-2022-10-05/

Design decisions:
- Uses lxml for XML generation (not string templates — avoids injection risks)
- Generates one context per (entity, period) pair
- One unit per currency (ISO 4217)
- Facts are sorted by account_code for deterministic output
- Amounts stored as strings to preserve decimal precision
"""

import hashlib
import logging
from datetime import date
from typing import Dict, List, Optional
from lxml import etree
from .models import FinancialFact, ReportEntity, ReportRequest

logger = logging.getLogger(__name__)

# XBRL 2.1 namespaces
NS_XBRL = "http://www.xbrl.org/2003/instance"
NS_LINK = "http://www.xbrl.org/2003/linkbase"
NS_XLINK = "http://www.w3.org/1999/xlink"
NS_ISO4217 = "http://www.xbrl.org/2003/iso4217"
NS_XBRLI = "http://www.xbrl.org/2003/instance"
NS_XHTML = "http://www.w3.org/1999/xhtml"
NS_IX = "http://www.xbrl.org/2013/inlineXBRL"

NSMAP = {
    None:      NS_XBRL,
    "link":    NS_LINK,
    "xlink":   NS_XLINK,
    "iso4217": NS_ISO4217,
    "xbrli":   NS_XBRLI,
}


def _context_id(entity_id: str, period_start: date, period_end: date) -> str:
    """Generate a stable context ID from entity + period."""
    raw = f"{entity_id}_{period_start.isoformat()}_{period_end.isoformat()}"
    return "ctx_" + hashlib.md5(raw.encode()).hexdigest()[:12]


def _unit_id(currency: str) -> str:
    return f"u_{currency.upper()}"


class XBRLGenerator:
    """Generates XBRL 2.1 instance documents from ReportRequest data.

    The generated XML conforms to the XBRL 2.1 specification. Specifically:
    - Uses `xbrli:context` with `xbrli:entity` and `xbrli:period`
    - Uses `xbrli:unit` with `xbrli:measure` (ISO 4217 currency)
    - Each fact element references a `contextRef` and (for monetary) `unitRef`
    - `decimals` attribute set to "2" for monetary amounts
    """

    def generate(self, request: ReportRequest) -> bytes:
        """Generate a XBRL 2.1 instance document.

        Returns:
            UTF-8 encoded XML bytes, ready for file storage.
        """
        # Root element with all namespace declarations
        root = etree.Element(
            "{%s}xbrl" % NS_XBRL,
            nsmap={
                None:        NS_XBRL,
                "link":      NS_LINK,
                "xlink":     NS_XLINK,
                "iso4217":   NS_ISO4217,
                "xbrli":     NS_XBRLI,
                "gl-plt":    "http://www.xbrl.org/taxonomy/int/gl/plt/2016-12-01",
            }
        )

        # Schema reference
        schema_ref = etree.SubElement(
            root,
            "{%s}schemaRef" % NS_LINK,
            {"{%s}type" % NS_XLINK: "simple",
             "{%s}href" % NS_XLINK: request.taxonomy_namespace}
        )

        # Build unique contexts and units from facts
        contexts_seen: Dict[str, bool] = {}
        units_seen: Dict[str, bool] = {}

        for fact in sorted(request.facts, key=lambda f: f.account_code):
            ctx_id = _context_id(request.entity.entity_id, fact.period_start, fact.period_end)
            unit_id = _unit_id(fact.currency)

            if ctx_id not in contexts_seen:
                self._add_context(root, ctx_id, request.entity, fact.period_start, fact.period_end)
                contexts_seen[ctx_id] = True

            if unit_id not in units_seen:
                self._add_unit(root, unit_id, fact.currency)
                units_seen[unit_id] = True

        # Add fact elements
        for fact in sorted(request.facts, key=lambda f: f.account_code):
            ctx_id = _context_id(request.entity.entity_id, fact.period_start, fact.period_end)
            unit_id = _unit_id(fact.currency)

            # Use the xbrl_concept if set, otherwise construct from account_code
            concept = fact.xbrl_concept or f"gl-plt:{fact.account_code.replace('.', '_')}"

            # Split prefix:localname
            if ':' in concept:
                prefix, local = concept.split(':', 1)
                ns = root.nsmap.get(prefix, NS_XBRL)
                tag = "{%s}%s" % (ns, local)
            else:
                tag = "{%s}%s" % (NS_XBRL, concept)

            elem = etree.SubElement(root, tag, {
                "contextRef": ctx_id,
                "unitRef": unit_id,
                "decimals": "2",
            })
            elem.text = f"{fact.amount:.2f}"

        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)

    def _add_context(
        self,
        root: etree._Element,
        ctx_id: str,
        entity: ReportEntity,
        period_start: date,
        period_end: date,
    ) -> None:
        ctx = etree.SubElement(root, "{%s}context" % NS_XBRL, {"id": ctx_id})
        ent = etree.SubElement(ctx, "{%s}entity" % NS_XBRL)
        ident = etree.SubElement(ent, "{%s}identifier" % NS_XBRL,
                                  {"scheme": "http://www.sec.gov/CIK"})
        ident.text = entity.entity_id

        period = etree.SubElement(ctx, "{%s}period" % NS_XBRL)
        start_elem = etree.SubElement(period, "{%s}startDate" % NS_XBRL)
        start_elem.text = period_start.isoformat()
        end_elem = etree.SubElement(period, "{%s}endDate" % NS_XBRL)
        end_elem.text = period_end.isoformat()

    def _add_unit(self, root: etree._Element, unit_id: str, currency: str) -> None:
        unit = etree.SubElement(root, "{%s}unit" % NS_XBRL, {"id": unit_id})
        measure = etree.SubElement(unit, "{%s}measure" % NS_XBRL)
        measure.text = f"iso4217:{currency.upper()}"


class IXBRLGenerator:
    """Generates iXBRL (Inline XBRL) embedded in an XHTML document.

    iXBRL embeds XBRL facts directly in human-readable HTML using ix: namespace
    tags. The resulting document is both human-readable and machine-parseable.

    Structure:
      <html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL">
        <head>
          <ix:header>
            <ix:references>...</ix:references>
            <ix:resources>
              <xbrli:context>...</xbrli:context>
              <xbrli:unit>...</xbrli:unit>
            </ix:resources>
          </ix:header>
        </head>
        <body>
          ... human-readable HTML with <ix:nonFraction> tags ...
        </body>
      </html>
    """

    def generate(self, request: ReportRequest) -> bytes:
        """Generate an iXBRL document."""
        NSMAP_IX = {
            "ix":      NS_IX,
            "xbrli":   NS_XBRLI,
            "iso4217": NS_ISO4217,
            "link":    NS_LINK,
            "xlink":   NS_XLINK,
            "gl-plt":  "http://www.xbrl.org/taxonomy/int/gl/plt/2016-12-01",
        }

        html = etree.Element("{%s}html" % NS_XHTML, nsmap={**NSMAP_IX, None: NS_XHTML})

        # Head with ix:header
        head = etree.SubElement(html, "{%s}head" % NS_XHTML)
        title_elem = etree.SubElement(head, "{%s}title" % NS_XHTML)
        title_elem.text = request.report_title or f"iXBRL Report — {request.period_start} to {request.period_end}"

        ix_header = etree.SubElement(head, "{%s}header" % NS_IX)
        ix_refs = etree.SubElement(ix_header, "{%s}references" % NS_IX)
        schema_ref = etree.SubElement(ix_refs, "{%s}schemaRef" % NS_LINK, {
            "{%s}type" % NS_XLINK: "simple",
            "{%s}href" % NS_XLINK: request.taxonomy_namespace,
        })

        ix_resources = etree.SubElement(ix_header, "{%s}resources" % NS_IX)

        # Add contexts and units into ix:resources
        contexts_seen: Dict[str, bool] = {}
        units_seen: Dict[str, bool] = {}

        for fact in request.facts:
            ctx_id = _context_id(request.entity.entity_id, fact.period_start, fact.period_end)
            unit_id = _unit_id(fact.currency)

            if ctx_id not in contexts_seen:
                ctx = etree.SubElement(ix_resources, "{%s}context" % NS_XBRLI, {"id": ctx_id})
                ent = etree.SubElement(ctx, "{%s}entity" % NS_XBRLI)
                ident = etree.SubElement(ent, "{%s}identifier" % NS_XBRLI, {"scheme": "http://www.sec.gov/CIK"})
                ident.text = request.entity.entity_id
                period = etree.SubElement(ctx, "{%s}period" % NS_XBRLI)
                s = etree.SubElement(period, "{%s}startDate" % NS_XBRLI)
                s.text = fact.period_start.isoformat()
                e = etree.SubElement(period, "{%s}endDate" % NS_XBRLI)
                e.text = fact.period_end.isoformat()
                contexts_seen[ctx_id] = True

            if unit_id not in units_seen:
                u = etree.SubElement(ix_resources, "{%s}unit" % NS_XBRLI, {"id": unit_id})
                m = etree.SubElement(u, "{%s}measure" % NS_XBRLI)
                m.text = f"iso4217:{fact.currency.upper()}"
                units_seen[unit_id] = True

        # Body with human-readable table + embedded ix:nonFraction tags
        body = etree.SubElement(html, "{%s}body" % NS_XHTML)
        h1 = etree.SubElement(body, "{%s}h1" % NS_XHTML)
        h1.text = request.report_title or "Financial Report"

        p = etree.SubElement(body, "{%s}p" % NS_XHTML)
        p.text = f"Period: {request.period_start.isoformat()} to {request.period_end.isoformat()} | Entity: {request.entity.entity_name}"

        table = etree.SubElement(body, "{%s}table" % NS_XHTML, {"border": "1", "cellpadding": "4"})
        thead = etree.SubElement(table, "{%s}thead" % NS_XHTML)
        hrow = etree.SubElement(thead, "{%s}tr" % NS_XHTML)
        for hdr in ("Account Code", "Account Name", "Amount", "Currency", "D/C"):
            th = etree.SubElement(hrow, "{%s}th" % NS_XHTML)
            th.text = hdr

        tbody = etree.SubElement(table, "{%s}tbody" % NS_XHTML)
        for fact in sorted(request.facts, key=lambda f: f.account_code):
            ctx_id = _context_id(request.entity.entity_id, fact.period_start, fact.period_end)
            unit_id = _unit_id(fact.currency)
            concept = fact.xbrl_concept or f"gl-plt:{fact.account_code.replace('.', '_')}"

            tr = etree.SubElement(tbody, "{%s}tr" % NS_XHTML)
            td_code = etree.SubElement(tr, "{%s}td" % NS_XHTML)
            td_code.text = fact.account_code
            td_name = etree.SubElement(tr, "{%s}td" % NS_XHTML)
            td_name.text = fact.account_name

            # Embedded iXBRL fact
            td_amt = etree.SubElement(tr, "{%s}td" % NS_XHTML)
            prefix, local = concept.split(":", 1) if ":" in concept else ("gl-plt", concept)
            ix_fact = etree.SubElement(td_amt, "{%s}nonFraction" % NS_IX, {
                "name": concept,
                "contextRef": ctx_id,
                "unitRef": unit_id,
                "decimals": "2",
                "format": "ixt:num-dot-decimal",
            })
            ix_fact.text = f"{fact.amount:.2f}"

            td_curr = etree.SubElement(tr, "{%s}td" % NS_XHTML)
            td_curr.text = fact.currency
            td_dc = etree.SubElement(tr, "{%s}td" % NS_XHTML)
            td_dc.text = fact.debit_credit

        return etree.tostring(html, xml_declaration=True, encoding="UTF-8", pretty_print=True,
                              doctype='<!DOCTYPE html>')
