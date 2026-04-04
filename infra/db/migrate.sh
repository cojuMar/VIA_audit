#!/bin/sh
# ---------------------------------------------------------------------------
# migrate.sh – Apply ordered SQL migrations for Project Aegis
#
# Applies every file matching V*.sql inside infra/db/migrations/ in
# lexicographic (version) order.  Exits immediately on the first failure.
#
# Usage:
#   DATABASE_URL=postgresql://user:pass@host:5432/db ./migrate.sh
#
# Defaults to the local dev connection string when DATABASE_URL is unset.
# ---------------------------------------------------------------------------
set -euo pipefail

DATABASE_URL="${DATABASE_URL:-postgresql://aegis_admin:aegis_dev_pw@localhost:5432/aegis}"

# Resolve the migrations directory relative to this script's location so the
# script works correctly regardless of the caller's working directory.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MIGRATIONS_DIR="${SCRIPT_DIR}/migrations"

if [ ! -d "${MIGRATIONS_DIR}" ]; then
  echo "[migrate] ERROR: Migrations directory not found: ${MIGRATIONS_DIR}" >&2
  exit 1
fi

# Collect V*.sql files sorted lexicographically (version order).
MIGRATION_FILES=$(find "${MIGRATIONS_DIR}" -maxdepth 1 -name "V*.sql" | sort)

if [ -z "${MIGRATION_FILES}" ]; then
  echo "[migrate] No migration files found in ${MIGRATIONS_DIR}. Nothing to do."
  exit 0
fi

echo "[migrate] Using database: ${DATABASE_URL}"
echo "[migrate] Migrations directory: ${MIGRATIONS_DIR}"
echo ""

APPLIED=0
FAILED=0

for MIGRATION_FILE in ${MIGRATION_FILES}; do
  FILENAME="$(basename "${MIGRATION_FILE}")"
  echo "[migrate] Applying: ${FILENAME} ..."

  if psql "${DATABASE_URL}" \
       --set ON_ERROR_STOP=1 \
       --single-transaction \
       --file="${MIGRATION_FILE}"; then
    echo "[migrate] OK: ${FILENAME}"
    APPLIED=$((APPLIED + 1))
  else
    echo "[migrate] FAILED: ${FILENAME}" >&2
    FAILED=$((FAILED + 1))
    echo "[migrate] Aborting after ${APPLIED} successful migration(s)." >&2
    exit 1
  fi
done

echo ""
echo "[migrate] Migration complete. Applied ${APPLIED} file(s)."
