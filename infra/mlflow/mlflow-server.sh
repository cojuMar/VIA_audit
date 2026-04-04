#!/bin/bash
# =============================================================================
# mlflow-server.sh
# Project Aegis 2026 – Sprint 3: Forensic AI & Anomaly Detection
# =============================================================================
# Purpose:
#   Starts the MLflow tracking server with PostgreSQL as the backend metadata
#   store and MinIO (S3-compatible) as the artifact store.
#
# Backend store (--backend-store-uri):
#   MLflow uses PostgreSQL to persist experiment metadata, run parameters,
#   metrics, and tags.  The database 'aegis_mlflow' must exist before this
#   script is invoked.  In docker-compose the postgres healthcheck ensures
#   the database is ready before this container starts.
#
# Artifact store (--default-artifact-root):
#   Model binaries, evaluation artefacts, and feature vectors are stored in
#   MinIO at the path s3://aegis-ml-artifacts/.  The S3 endpoint is overridden
#   to point at the local MinIO instance via the MLFLOW_S3_ENDPOINT_URL
#   environment variable (set in docker-compose).
#
# Artifact serving (--serve-artifacts):
#   Enables the MLflow server to proxy artifact downloads via its own API,
#   so client services do not need direct MinIO credentials in production.
#
# Environment variables (all have safe defaults for local dev):
#   MLFLOW_BACKEND_URI   – PostgreSQL DSN for metadata store
#   MLFLOW_ARTIFACT_ROOT – S3 URI for artifact storage root
#
# Usage:
#   The script is executed as the container ENTRYPOINT by the mlflow service
#   in docker-compose.yml.  It can also be run directly for local testing:
#
#     export MLFLOW_BACKEND_URI="postgresql://..."
#     export MLFLOW_ARTIFACT_ROOT="s3://aegis-ml-artifacts/"
#     ./infra/mlflow/mlflow-server.sh
#
# =============================================================================
set -euo pipefail

# exec replaces the shell process with mlflow so signals (SIGTERM, SIGINT)
# are delivered directly to mlflow rather than to a wrapper shell.
exec mlflow server \
  --backend-store-uri  "${MLFLOW_BACKEND_URI:-postgresql://aegis_admin:aegis_dev_pw@postgres:5432/aegis_mlflow}" \
  --default-artifact-root "${MLFLOW_ARTIFACT_ROOT:-s3://aegis-ml-artifacts/}" \
  --host 0.0.0.0 \
  --port 5000 \
  --serve-artifacts
