#!/usr/bin/env bash
# =============================================================================
# Sprint 29 — coverage gate for security-critical services.
#
# For each service in SECURITY_CRITICAL we:
#   1. cd into services/<svc>
#   2. run `coverage run -m pytest tests/`
#   3. read the line-coverage percentage out of `coverage report`
#   4. fail if it's below COVERAGE_MIN
#
# A missing tests/ directory or a service that yields zero coverage is
# treated as a hard failure — Sprint 29 is exactly the sprint that adds
# those tests, so a regression past this point should not be silent.
# =============================================================================
set -euo pipefail

COVERAGE_MIN=${COVERAGE_MIN:-60}

# Python services only — zk-proof-worker is Rust and has its own
# `cargo test`-based gate (see services/zk-proof-worker/tests/).
SECURITY_CRITICAL=(
  "auth-service"
  "pam-broker"
  "tenant-registry"
  "pq-crypto-service"
  "evidence-store"
  "forensic-ml-service"
)

failures=()

for svc in "${SECURITY_CRITICAL[@]}"; do
  svc_dir="services/${svc}"
  if [[ ! -d "${svc_dir}/tests" ]]; then
    echo "::error::${svc} has no tests/ directory — Sprint 29 requires one."
    failures+=("${svc}: no tests/ dir")
    continue
  fi

  echo "── ${svc} ───────────────────────────────────────────────"
  pushd "${svc_dir}" >/dev/null

  # We run with --rootdir pointing at the service so tests stay self-contained.
  if ! coverage run --source=src -m pytest tests/ -q; then
    echo "::error::${svc} pytest failed"
    failures+=("${svc}: pytest failed")
    popd >/dev/null
    continue
  fi

  pct=$(coverage report --format=total 2>/dev/null || echo 0)
  echo "${svc} coverage: ${pct}%"
  if (( $(echo "${pct} < ${COVERAGE_MIN}" | bc -l) )); then
    echo "::error::${svc} coverage ${pct}% is below the ${COVERAGE_MIN}% gate"
    failures+=("${svc}: ${pct}% < ${COVERAGE_MIN}%")
  fi

  popd >/dev/null
done

if (( ${#failures[@]} > 0 )); then
  echo "Coverage gate failed:"
  printf '  - %s\n' "${failures[@]}"
  exit 1
fi
echo "Coverage gate passed for all ${#SECURITY_CRITICAL[@]} security-critical services."
