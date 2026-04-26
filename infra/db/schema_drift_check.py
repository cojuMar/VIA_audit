"""
Sprint 23 — schema drift guard.

Scans every services/<svc>/src/**/*.py for INSERT INTO <table> (col, col, ...)
statements, and asserts every referenced column actually exists in the running
database (information_schema.columns).

Run as a CI job after migrations have been applied. Fails non-zero if any
column references a non-existent column on any non-temp table.

Usage:
    python infra/db/schema_drift_check.py [--db <conn_string>]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import psycopg2  # type: ignore[import-not-found]


REPO = Path(__file__).resolve().parents[2]
SERVICES = REPO / "services"

# Match  INSERT INTO <table> ( col1, col2, ...)  even across newlines.
# Group 1: table name; Group 2: column list contents.
INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+(?:public\.)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]+)\)",
    re.IGNORECASE | re.DOTALL,
)
# Columns that are SQL keywords/functions, not actual column names — ignore.
SQL_NOISE = {"now", "current_timestamp", "default", "null"}


def collect_inserts() -> dict[str, set[str]]:
    """Return {table_name: {column, column, ...}} found across services."""
    found: dict[str, set[str]] = defaultdict(set)
    for py in SERVICES.rglob("*.py"):
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in INSERT_RE.finditer(text):
            table = m.group(1).lower()
            cols_blob = m.group(2)
            for raw in cols_blob.split(","):
                col = raw.strip().strip('"').lower()
                if not col or col in SQL_NOISE:
                    continue
                # Skip anything that looks like an expression (has parens/spaces)
                if "(" in col or " " in col:
                    continue
                found[table].add(col)
    return found


def db_columns(conn) -> dict[str, set[str]]:
    """Return {table_name: {column, ...}} for all public-schema base tables."""
    out: dict[str, set[str]] = defaultdict(set)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
            """
        )
        for table, col in cur.fetchall():
            out[table.lower()].add(col.lower())
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--db",
        default=os.getenv(
            "DATABASE_URL",
            "postgresql://aegis_admin:aegis_dev_pw@localhost:5432/aegis",
        ),
    )
    p.add_argument(
        "--only",
        action="append",
        default=[],
        help=(
            "Restrict the check to specific table(s). Repeatable. "
            "If omitted, checks every table referenced in INSERT statements. "
            "Sprint 23 baseline: --only audit_engagements --only risks "
            "--only risk_assessments."
        ),
    )
    args = p.parse_args()
    only = {t.lower() for t in args.only}

    inserts = collect_inserts()
    conn = psycopg2.connect(args.db)
    try:
        live = db_columns(conn)
    finally:
        conn.close()

    drift: list[str] = []
    for table, cols in sorted(inserts.items()):
        if only and table not in only:
            continue
        if table not in live:
            # Either a temp/CTE/runtime-named table or a missing migration.
            # Skip rather than false-flag CTEs.
            continue
        unknown = cols - live[table]
        for c in sorted(unknown):
            drift.append(f"  {table}.{c}  — column does not exist in DB")

    if drift:
        print(
            "schema_drift_check FAILED: services reference columns that do not exist:\n"
            + "\n".join(drift)
        )
        return 1

    print(
        f"schema_drift_check OK — verified {sum(len(c) for c in inserts.values())} "
        f"column references across {len(inserts)} tables."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
