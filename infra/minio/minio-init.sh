#!/usr/bin/env bash
# =============================================================================
# minio-init.sh
# Project: Aegis 2026 – Sprint 2 – Zero-Touch Evidence Engine
#
# Purpose:
#   One-shot initialisation script executed by the minio-init container.
#   Creates all required MinIO buckets with WORM object-locking, retention
#   policies, and lifecycle rules for the Aegis evidence ingestion pipeline.
#
# Buckets created:
#   aegis-evidence-worm   – WORM evidence store (COMPLIANCE, 365-day retention)
#   aegis-zk-proofs       – ZK proof blobs     (COMPLIANCE, 2555-day / 7-year)
#   aegis-reports         – Generated exports  (no lock; reports are reproducible)
#
# Prerequisites:
#   * MinIO server is healthy at http://minio:9000
#   * MINIO_ROOT_USER and MINIO_ROOT_PASSWORD are set in the environment
#   * minio/mc image provides the `mc` binary
#
# Usage (via docker-compose):
#   The minio-init service mounts this script and runs it as its entrypoint.
#   Restart policy is "no" so it runs exactly once per `docker compose up`.
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ALIAS="aegis"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://minio:9000}"
MINIO_USER="${MINIO_ROOT_USER:?MINIO_ROOT_USER must be set}"
MINIO_PASS="${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD must be set}"

# Bucket names
BUCKET_EVIDENCE="aegis-evidence-worm"
BUCKET_PROOFS="aegis-zk-proofs"
BUCKET_REPORTS="aegis-reports"

# Retention periods
EVIDENCE_RETENTION_DAYS=365
PROOFS_RETENTION_DAYS=2555      # 7 years (2555 = 365 * 7)

# Lifecycle: transition evidence objects to cold tier after this many days
EVIDENCE_GLACIER_DAYS=90

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
log()  { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] INFO  $*"; }
warn() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] WARN  $*" >&2; }
die()  { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] ERROR $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Step 1: Wait for MinIO to be healthy
# Poll until `mc alias set` succeeds, backing off exponentially.
# ---------------------------------------------------------------------------
wait_for_minio() {
    log "Waiting for MinIO to be healthy at ${MINIO_ENDPOINT} ..."
    local attempt=0
    local max_attempts=30
    local sleep_sec=2

    while true; do
        attempt=$(( attempt + 1 ))
        if mc alias set "${ALIAS}" "${MINIO_ENDPOINT}" \
               "${MINIO_USER}" "${MINIO_PASS}" \
               --api S3v4 > /dev/null 2>&1; then
            log "MinIO is healthy (attempt ${attempt})."
            return 0
        fi

        if [ "${attempt}" -ge "${max_attempts}" ]; then
            die "MinIO did not become healthy after ${max_attempts} attempts. Aborting."
        fi

        warn "MinIO not ready yet (attempt ${attempt}/${max_attempts}). Retrying in ${sleep_sec}s ..."
        sleep "${sleep_sec}"

        # Exponential back-off, capped at 30 s
        sleep_sec=$(( sleep_sec < 30 ? sleep_sec * 2 : 30 ))
    done
}

# ---------------------------------------------------------------------------
# Step 2: Set MinIO alias
# Re-runs after the health loop to ensure the alias is registered cleanly.
# ---------------------------------------------------------------------------
configure_alias() {
    log "Configuring mc alias '${ALIAS}' → ${MINIO_ENDPOINT} ..."
    mc alias set "${ALIAS}" "${MINIO_ENDPOINT}" \
        "${MINIO_USER}" "${MINIO_PASS}" \
        --api S3v4
    log "Alias configured."
}

# ---------------------------------------------------------------------------
# Helper: create a bucket only if it does not already exist
# ---------------------------------------------------------------------------
create_bucket_if_not_exists() {
    local bucket="$1"
    local with_lock="${2:-false}"   # pass "true" to enable object locking

    if mc ls "${ALIAS}/${bucket}" > /dev/null 2>&1; then
        log "Bucket '${bucket}' already exists — skipping creation."
        return 0
    fi

    log "Creating bucket '${bucket}' (object-lock=${with_lock}) ..."
    if [ "${with_lock}" = "true" ]; then
        # --with-lock enables the S3 object locking feature at bucket creation.
        # This flag CANNOT be added after the bucket exists — it must be set now.
        mc mb --with-lock "${ALIAS}/${bucket}"
    else
        mc mb "${ALIAS}/${bucket}"
    fi
    log "Bucket '${bucket}' created."
}

# ---------------------------------------------------------------------------
# Step 3 & 4: aegis-evidence-worm
# WORM compliance storage for raw ingested evidence records.
# Retention: COMPLIANCE mode, 365 days.
# ---------------------------------------------------------------------------
init_evidence_bucket() {
    log "--- Initialising bucket: ${BUCKET_EVIDENCE} ---"
    create_bucket_if_not_exists "${BUCKET_EVIDENCE}" "true"

    # Enable object locking (idempotent — safe to call on an already-locked bucket).
    log "Enabling object locking on '${BUCKET_EVIDENCE}' ..."
    mc object-lock enable "${ALIAS}/${BUCKET_EVIDENCE}" || \
        log "Object locking already enabled on '${BUCKET_EVIDENCE}'."

    # Set the default retention: COMPLIANCE mode, 365-day minimum hold.
    # COMPLIANCE mode means even the root user cannot delete locked objects.
    log "Setting default retention: COMPLIANCE ${EVIDENCE_RETENTION_DAYS}d on '${BUCKET_EVIDENCE}' ..."
    mc object-lock set \
        --mode COMPLIANCE \
        --validity "${EVIDENCE_RETENTION_DAYS}" \
        --unit "d" \
        "${ALIAS}/${BUCKET_EVIDENCE}"
    log "Retention policy set on '${BUCKET_EVIDENCE}'."
}

# ---------------------------------------------------------------------------
# Step 5 (lifecycle): evidence-worm → GLACIER transition after 90 days
# MinIO ILM lifecycle rule: move objects to the GLACIER tier after
# EVIDENCE_GLACIER_DAYS days to reduce hot-tier storage costs.
# ---------------------------------------------------------------------------
set_evidence_lifecycle() {
    log "Setting ILM lifecycle on '${BUCKET_EVIDENCE}' (GLACIER after ${EVIDENCE_GLACIER_DAYS}d) ..."

    # Build a minimal S3-compatible lifecycle policy JSON.
    # MinIO's `mc ilm import` accepts this format.
    local lifecycle_json
    lifecycle_json=$(cat <<EOF
{
  "Rules": [
    {
      "ID":     "transition-evidence-to-glacier",
      "Status": "Enabled",
      "Filter": { "Prefix": "" },
      "Transitions": [
        {
          "Days":         ${EVIDENCE_GLACIER_DAYS},
          "StorageClass": "GLACIER"
        }
      ]
    }
  ]
}
EOF
)

    echo "${lifecycle_json}" | mc ilm import "${ALIAS}/${BUCKET_EVIDENCE}" || \
        warn "ILM import failed — MinIO tier may not be configured. Lifecycle rule skipped."
    log "ILM lifecycle configured on '${BUCKET_EVIDENCE}'."
}

# ---------------------------------------------------------------------------
# Steps 6 & 7: aegis-zk-proofs
# WORM compliance storage for ZK proof blobs.
# Retention: COMPLIANCE mode, 2555 days (7 years) to satisfy SOX/PCAOB
# requirements for audit evidence retention.
# ---------------------------------------------------------------------------
init_proofs_bucket() {
    log "--- Initialising bucket: ${BUCKET_PROOFS} ---"
    create_bucket_if_not_exists "${BUCKET_PROOFS}" "true"

    log "Enabling object locking on '${BUCKET_PROOFS}' ..."
    mc object-lock enable "${ALIAS}/${BUCKET_PROOFS}" || \
        log "Object locking already enabled on '${BUCKET_PROOFS}'."

    log "Setting default retention: COMPLIANCE ${PROOFS_RETENTION_DAYS}d on '${BUCKET_PROOFS}' ..."
    mc object-lock set \
        --mode COMPLIANCE \
        --validity "${PROOFS_RETENTION_DAYS}" \
        --unit "d" \
        "${ALIAS}/${BUCKET_PROOFS}"
    log "Retention policy set on '${BUCKET_PROOFS}'."
}

# ---------------------------------------------------------------------------
# Step 8: aegis-reports
# Mutable bucket for generated exports (XBRL, SAF-T, PDF audit packs, etc.).
# No object lock — reports can be regenerated from the immutable evidence
# and ZK-proof stores at any time.
# ---------------------------------------------------------------------------
init_reports_bucket() {
    log "--- Initialising bucket: ${BUCKET_REPORTS} ---"
    create_bucket_if_not_exists "${BUCKET_REPORTS}" "false"
    log "Bucket '${BUCKET_REPORTS}' ready (no object lock)."
}

# ---------------------------------------------------------------------------
# Step 10: Print summary
# ---------------------------------------------------------------------------
print_summary() {
    log "=========================================="
    log "MinIO initialisation complete."
    log "=========================================="
    log ""
    log "Buckets:"
    mc ls "${ALIAS}" | while read -r _date _time _size bucket; do
        log "  • ${bucket}"
    done
    log ""
    log "Object lock status:"
    for bucket in "${BUCKET_EVIDENCE}" "${BUCKET_PROOFS}"; do
        local lock_info
        lock_info=$(mc object-lock info "${ALIAS}/${bucket}" 2>&1 || echo "(error reading lock)")
        log "  ${bucket}: ${lock_info}"
    done
    log ""
    log "All done. This container will now exit (restart: no)."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    log "Starting Aegis MinIO initialisation ..."
    log "  Endpoint : ${MINIO_ENDPOINT}"
    log "  User     : ${MINIO_USER}"
    log ""

    wait_for_minio
    configure_alias

    init_evidence_bucket
    set_evidence_lifecycle

    init_proofs_bucket

    init_reports_bucket

    print_summary
}

main "$@"
