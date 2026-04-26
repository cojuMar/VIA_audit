#!/usr/bin/env bash
# =============================================================================
# Sprint 30 — TypeScript dead-export check via ts-prune.
#
# Walks every UI's tsconfig and reports exports that no other file imports.
# An allowlist (`ALLOWED_PATTERNS`) covers genuine public exports that
# ts-prune can't see (entry-point modules, types re-exported for consumers
# of @via/api-client / @via/ui-kit, etc.).
# =============================================================================
set -euo pipefail

# Patterns ts-prune is allowed to report without failing the build.
# Keep this list small — every entry should be justified in a comment.
ALLOWED_PATTERNS=(
  # Entry points — Vite imports them, ts-prune can't follow that.
  'src/main.tsx'
  'src/App.tsx'
  # Package barrels — re-exported for downstream UIs.
  'packages/api-client/src/index.ts'
  'packages/ui-kit/src/index.ts'
  # Used in JSX type position only — ts-prune misses these.
  'used in module'
)

# Each UI is a separate tsconfig root.
UIS=(
  services/hub-ui
  services/dashboard-ui
  services/risk-ui
  services/pbc-ui
  services/audit-planning-ui
  services/esg-board-ui
  services/people-ui
  services/monitoring-ui
  services/integration-ui
  services/tprm-ui
  services/trust-portal-ui
  services/ai-agent-ui
  services/framework-ui
)

# Make the allow-pattern grep filter from the array.
filter=$(printf '|%s' "${ALLOWED_PATTERNS[@]}")
filter="${filter:1}"

failures=0

for ui in "${UIS[@]}"; do
  if [[ ! -f "${ui}/tsconfig.json" ]]; then
    echo "skip ${ui} (no tsconfig.json)"
    continue
  fi
  echo "── ${ui} ────────────────────────────────"
  # `ts-prune` exits 0 even when it finds dead code, so we drive the gate
  # off the line count after the allowlist filter.
  raw=$(npx --yes ts-prune -p "${ui}/tsconfig.json" 2>/dev/null || true)
  filtered=$(echo "${raw}" | grep -Ev "(${filter})" || true)
  if [[ -n "${filtered}" ]]; then
    echo "::error::${ui} has dead exports:"
    echo "${filtered}"
    failures=$((failures + 1))
  fi
done

if (( failures > 0 )); then
  echo "ts-prune gate failed for ${failures} UI(s)."
  exit 1
fi
echo "ts-prune gate passed for ${#UIS[@]} UIs."
