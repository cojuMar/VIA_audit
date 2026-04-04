#!/usr/bin/env bash
# =============================================================================
# kafka-topics.sh
# Project: Aegis 2026 – Sprint 2 – Zero-Touch Evidence Engine
#
# Purpose:
#   One-shot initialisation script executed by the kafka-init container.
#   Creates all required Kafka topics for the Aegis evidence pipeline with
#   appropriate partition counts, replication factors, and retention settings.
#
# Topic inventory:
#   aegis.evidence.ingested        – raw ingested evidence from connectors
#   aegis.evidence.normalized      – normalised canonical evidence records
#   aegis.zk.proof.requested       – ZK proof generation requests
#   aegis.zk.proof.completed       – ZK proof completion events
#   aegis.ml.anomaly.requested     – ML anomaly detection requests
#   aegis.audit.events             – platform-wide audit log stream
#   aegis.connectors.health        – connector health/heartbeat events
#
# Design notes:
#   * Partition counts are tuned for the target dev/staging throughput.
#     Scale to 32+ partitions per high-volume topic in production.
#   * Replication factor is 1 for local development (single-broker cluster).
#     Set to 3 in staging/production Helm values.
#   * Retention is set via topic-level configuration overrides.
#   * auto.create.topics.enable=false on the broker ensures only explicitly
#     created topics are available — any typo fails fast.
#   * `--if-not-exists` flag prevents errors on re-runs (idempotent).
#
# Usage (via docker-compose):
#   The kafka-init service mounts this script and runs it as its entrypoint.
#   Restart policy is "no" so it runs exactly once per `docker compose up`.
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration (override via environment variables if needed)
# ---------------------------------------------------------------------------
BOOTSTRAP_SERVER="${KAFKA_BOOTSTRAP_SERVER:-kafka:29092}"
REPLICATION_FACTOR="${KAFKA_REPLICATION_FACTOR:-1}"

# kafka-topics command (available in the confluentinc/cp-kafka image)
KAFKA_TOPICS_CMD="kafka-topics"

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
log()  { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] INFO  $*"; }
warn() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] WARN  $*" >&2; }
die()  { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] ERROR $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Step 1: Wait for Kafka broker to be ready
# Polls `kafka-topics --list` until the broker accepts connections.
# ---------------------------------------------------------------------------
wait_for_kafka() {
    log "Waiting for Kafka broker at ${BOOTSTRAP_SERVER} ..."
    local attempt=0
    local max_attempts=30
    local sleep_sec=3

    while true; do
        attempt=$(( attempt + 1 ))
        if ${KAFKA_TOPICS_CMD} \
               --bootstrap-server "${BOOTSTRAP_SERVER}" \
               --list > /dev/null 2>&1; then
            log "Kafka broker is ready (attempt ${attempt})."
            return 0
        fi

        if [ "${attempt}" -ge "${max_attempts}" ]; then
            die "Kafka broker at ${BOOTSTRAP_SERVER} did not become ready after ${max_attempts} attempts. Aborting."
        fi

        warn "Kafka not ready (attempt ${attempt}/${max_attempts}). Retrying in ${sleep_sec}s ..."
        sleep "${sleep_sec}"
    done
}

# ---------------------------------------------------------------------------
# Helper: create a topic with retention and partition settings.
#
# Arguments:
#   $1 topic name
#   $2 partition count
#   $3 retention.ms  (-1 = infinite, positive integer = milliseconds)
#   $4 [optional] additional --config flags as a single string
# ---------------------------------------------------------------------------
create_topic() {
    local topic="$1"
    local partitions="$2"
    local retention_ms="$3"
    local extra_config="${4:-}"

    log "Creating topic '${topic}' (partitions=${partitions}, retention=${retention_ms}ms) ..."

    # Build the base command
    local cmd="${KAFKA_TOPICS_CMD} \
        --bootstrap-server ${BOOTSTRAP_SERVER} \
        --create \
        --if-not-exists \
        --topic ${topic} \
        --partitions ${partitions} \
        --replication-factor ${REPLICATION_FACTOR} \
        --config retention.ms=${retention_ms}"

    # Append any extra per-topic config overrides
    if [ -n "${extra_config}" ]; then
        cmd="${cmd} ${extra_config}"
    fi

    # Execute
    eval "${cmd}"
    log "Topic '${topic}' ready."
}

# ---------------------------------------------------------------------------
# Retention constants (milliseconds)
# ---------------------------------------------------------------------------
RETENTION_1H=$((     1 * 60 * 60 * 1000 ))       #       3,600,000 ms
RETENTION_24H=$((   24 * 60 * 60 * 1000 ))       #      86,400,000 ms
RETENTION_7D=$((     7 * 24 * 60 * 60 * 1000 ))  #     604,800,000 ms
RETENTION_30D=$((   30 * 24 * 60 * 60 * 1000 ))  #   2,592,000,000 ms

# ---------------------------------------------------------------------------
# Step 2: aegis.evidence.ingested
# Raw evidence payloads emitted by the ingestion-orchestrator immediately
# after a successful connector poll.  High-throughput; 16 partitions.
# Retention: 7 days (downstream normaliser is expected to consume promptly).
# ---------------------------------------------------------------------------
create_topic \
    "aegis.evidence.ingested" \
    16 \
    "${RETENTION_7D}" \
    "--config compression.type=lz4 --config max.message.bytes=5242880"

# ---------------------------------------------------------------------------
# Step 3: aegis.evidence.normalized
# Canonical evidence records after field mapping and enrichment.
# Consumed by the ZK proof worker and ML anomaly service.
# Retention: 7 days (same window as the raw topic for replay alignment).
# ---------------------------------------------------------------------------
create_topic \
    "aegis.evidence.normalized" \
    16 \
    "${RETENTION_7D}" \
    "--config compression.type=lz4 --config max.message.bytes=5242880"

# ---------------------------------------------------------------------------
# Step 4: aegis.zk.proof.requested
# Proof generation requests emitted by the evidence normaliser once a batch
# of evidence records is ready.  Lower throughput than evidence topics;
# 8 partitions aligns with the expected number of ZK worker pods.
# Retention: 24 h — proof requests that are not consumed within a day
# indicate a worker outage and must be replayed from the database queue.
# ---------------------------------------------------------------------------
create_topic \
    "aegis.zk.proof.requested" \
    8 \
    "${RETENTION_24H}" \
    "--config compression.type=lz4"

# ---------------------------------------------------------------------------
# Step 5: aegis.zk.proof.completed
# Proof completion events emitted by the ZK proof worker after a proof blob
# is written to MinIO and the database row is updated.
# Retention: 24 h.
# ---------------------------------------------------------------------------
create_topic \
    "aegis.zk.proof.completed" \
    8 \
    "${RETENTION_24H}" \
    "--config compression.type=lz4"

# ---------------------------------------------------------------------------
# Step 6: aegis.ml.anomaly.requested
# Anomaly detection requests for the ML inference service.
# 16 partitions — same throughput envelope as the evidence topics.
# Retention: 7 days.
# ---------------------------------------------------------------------------
create_topic \
    "aegis.ml.anomaly.requested" \
    16 \
    "${RETENTION_7D}" \
    "--config compression.type=lz4"

# ---------------------------------------------------------------------------
# Step 7: aegis.audit.events
# Platform-wide audit log: authentication events, API calls, admin actions.
# Low write volume but long retention (30 days) for security investigations.
# 4 partitions is sufficient; increase to 8 in production.
# ---------------------------------------------------------------------------
create_topic \
    "aegis.audit.events" \
    4 \
    "${RETENTION_30D}" \
    "--config compression.type=gzip"

# ---------------------------------------------------------------------------
# Step 8: aegis.connectors.health
# Heartbeat and circuit-breaker state events from connector pollers.
# Very high write frequency (one message per poll attempt) but very short
# retention (1 hour) — consumers only care about the current state.
# ---------------------------------------------------------------------------
create_topic \
    "aegis.connectors.health" \
    4 \
    "${RETENTION_1H}" \
    "--config compression.type=lz4 --config cleanup.policy=compact"

# ---------------------------------------------------------------------------
# Step 9: Print summary
# ---------------------------------------------------------------------------
log ""
log "=========================================="
log "Kafka topic initialisation complete."
log "=========================================="
log ""
log "All topics:"
${KAFKA_TOPICS_CMD} \
    --bootstrap-server "${BOOTSTRAP_SERVER}" \
    --list \
    | grep "^aegis\." \
    | sort \
    | while read -r topic; do
        log "  • ${topic}"
      done
log ""
log "All done. This container will now exit (restart: no)."
