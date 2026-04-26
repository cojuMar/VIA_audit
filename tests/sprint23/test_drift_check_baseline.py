"""
Run the schema-drift CI guard against the Sprint 23 baseline tables and
require zero drift. This exists so a future migration that drops or renames
a column on these tables (without updating the service) fails CI.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "infra" / "db" / "schema_drift_check.py"


def test_sprint23_tables_have_no_drift():
    db = os.getenv(
        "DATABASE_URL",
        "postgresql://aegis_admin:aegis_dev_pw@localhost:5432/aegis",
    )
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--db", db,
            "--only", "audit_engagements",
            "--only", "risks",
            "--only", "risk_assessments",
            "--only", "risk_score_history",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"schema_drift_check failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
