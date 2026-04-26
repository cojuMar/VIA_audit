"""Source-level lint: no service is still using set_config(..., false)."""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVICES = REPO / "services"
PATTERN = re.compile(
    r"""set_config\(\s*['"]app\.tenant_id['"]\s*,\s*\$1\s*,\s*false\s*\)""",
    re.IGNORECASE,
)


def test_no_session_scoped_set_config():
    offenders: list[str] = []
    for py in SERVICES.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        if PATTERN.search(text):
            offenders.append(str(py.relative_to(REPO)))
    assert offenders == [], (
        "Session-scoped set_config remains — unsafe under PgBouncer "
        f"transaction pooling: {offenders}"
    )
