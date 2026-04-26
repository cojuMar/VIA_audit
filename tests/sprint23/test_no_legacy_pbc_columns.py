"""
pbc-service no longer references legacy audit_engagements column names
(engagement_name, engagement_type, period_start, period_end, description)
in INSERT/SELECT statements without an alias to the canonical name.

We allow them as SELECT aliases (e.g. `SELECT title AS engagement_name`)
because export payloads keep the legacy keys for client compatibility.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PBC_SRC = REPO / "services" / "pbc-service" / "src"

# Match a bare INSERT INTO audit_engagements (...) column list referencing legacy names.
INSERT_LEGACY = re.compile(
    r"INSERT\s+INTO\s+audit_engagements\s*\([^)]*"
    r"(engagement_name|engagement_type|period_start|period_end|description)",
    re.IGNORECASE | re.DOTALL,
)


def test_no_pbc_inserts_with_legacy_columns():
    offenders: list[str] = []
    for py in PBC_SRC.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        if INSERT_LEGACY.search(text):
            offenders.append(str(py.relative_to(REPO)))
    assert offenders == [], (
        f"pbc-service still inserts legacy column names into "
        f"audit_engagements: {offenders}. Use canonical names "
        "(title, audit_type, planned_start_date, planned_end_date, scope)."
    )
