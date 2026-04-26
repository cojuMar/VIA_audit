# VIA Platform Remediation Sprints

Derived from the Sprint-20 code review. Sprints are ordered by blast radius. Each sprint is sized for ~1 week of focused work and ends with demonstrable acceptance criteria. Nothing in Sprint 23+ should ship before Sprints 21 and 22 land.

---

## Sprint 21 — Auth Hardening (🔴 CRITICAL, week 1)

**Goal:** Close the authentication bypass and data-plane holes in auth-service. Nothing else matters until this is done.

### Scope
1. **Enforce JWT on every endpoint** in `services/auth-service/src/main.py`.
   - Add `Depends(get_current_user)` to `/auth/notifications` (GET/POST/PATCH/read/read-all/delete) and `/auth/search`.
   - Derive `tenant_id` exclusively from `user["tenant_id"]` — delete every body/query `tenant_id` parameter.
2. **Fix `/auth/register`** (main.py:286):
   - Drop `role` and `tenant_id` from the public body model.
   - Force `role="end_user"`; require an authenticated admin JWT for elevated roles (new `/auth/admin/invite-user` endpoint).
3. **Fix `/auth/login`** (main.py:240):
   - Remove `tenant_id` from login body; look up user by email only, take tenant from the user row.
4. **CORS tighten** (main.py:169):
   - Replace `allow_origins=["*"]` with explicit list from `CORS_ORIGINS` env var; keep `allow_credentials=True`.
5. **Parameterize every `SET app.tenant_id`** — 10 call sites (main.py:71, 134, 246, 366, 395, 412, 429, 447, 462, 483).
   - Swap `f"SET app.tenant_id = '{tenant_id}'"` → `"SELECT set_config('app.tenant_id', $1, true)"` wrapped in a transaction.
6. **JWT_SECRET hardening** (main.py:25, docker-compose.yml:721,1247):
   - Remove default; raise `RuntimeError` on startup if unset and `ENV != "dev"`.

### Acceptance
- `curl -X POST /auth/register -d '{"role":"super_admin",...}'` returns 403 / ignores role.
- `curl /auth/search -d '{"tenant_id":"<other-tenant>"}'` returns 401 without JWT, 403 with JWT from different tenant.
- New integration test: `tests/sprint21/test_auth_bypass.py` covers all 4 attack patterns found in the audit.
- `SET app.tenant_id = '<sqli>'` attempts return harmless error, not table drop.

### Deliverables
- Patch to `services/auth-service/src/main.py` + models.
- `tests/sprint21/` — regression suite for every CVE-class bug above.
- Updated `docker-compose.yml` removing `JWT_SECRET` default.

---

## Sprint 22 — RLS Actually Works (🔴 CRITICAL, week 2)

**Goal:** Make Row-Level Security enforce tenant isolation in the running system. Today it doesn't.

### Scope
1. **Create `aegis_app` role** — new migration `infra/db/migrations/V000__create_roles.sql` (or V027, renumber as needed):
   ```sql
   CREATE ROLE aegis_app LOGIN PASSWORD :'AEGIS_APP_PW' NOINHERIT;
   GRANT USAGE ON SCHEMA public TO aegis_app;
   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aegis_app;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO aegis_app;
   ```
2. **Switch all services off `aegis_admin`** in `docker-compose.yml` lines 157, 179, 298, 327, 352, 418, 606, 636, 671, 1073, 1129, 1189:
   - `pam-broker`, `tenant-registry`, `ingestion-orchestrator`, `evidence-store`, `zk-proof-worker`, `pq-crypto-service`, `framework-service`, `tprm-service`, `audit-planning-service`, `esg-board-service`, `mobile-sync-service` — repoint `DATABASE_URL` to `aegis_app`.
3. **`FORCE ROW LEVEL SECURITY`** — new migration that runs
   `ALTER TABLE <t> FORCE ROW LEVEL SECURITY;` on every table with RLS enabled.
4. **Audit RLS policy coverage** — add CI check:
   ```sql
   SELECT tablename FROM pg_tables t
   WHERE rowsecurity AND NOT EXISTS (
     SELECT 1 FROM pg_policies p WHERE p.tablename = t.tablename
   );
   ```
   Fail pipeline if any rows return.
5. **Fix PgBouncer transaction-pooling tenant leak**:
   - Replace `set_config('app.tenant_id', $1, false)` (session scope) with `set_config(..., true)` (transaction scope) across all services, wrapped in explicit `BEGIN`/`COMMIT`.
   - Grep target: `rag-pipeline-service/src/retriever.py:63` and ~30 others.

### Acceptance
- Integration test: connect as `aegis_app`, set `app.tenant_id` to tenant A, `SELECT * FROM audit_engagements` returns only A's rows.
- Same test as `aegis_admin` also returns only A's rows (proves FORCE works).
- CI job fails if any RLS-enabled table lacks a `tenant_isolation` policy.

---

## Sprint 23 — Schema Reconciliation (🔴 CRITICAL, week 3)

**Goal:** Fix the two duplicate-schema bugs that make audit-planning-service and risk-service non-functional.

### Scope
1. **`V027__reconcile_audit_engagements.sql`**:
   - `ALTER TABLE audit_engagements RENAME COLUMN engagement_name TO title;`
   - `... RENAME engagement_type TO audit_type;`
   - `... RENAME period_start TO planned_start_date;`
   - `... RENAME period_end TO planned_end_date;`
   - `ADD COLUMN` for: `plan_item_id`, `engagement_code`, `scope`, `objectives`, `budget_hours`, `team_members`, `engagement_manager`, `status_notes`.
   - Drop the duplicate `CREATE TABLE` block in V021.
2. **Update pbc-service** to match new schema:
   - `services/pbc-service/src/models.py` — rename fields or add translation layer.
   - `services/pbc-service/src/engagement_manager.py`, `src/export_engine.py` — update all SQL.
3. **Update audit-planning-service** — already targets V021 shape; just confirm end-to-end works after V027 lands.
4. **Fix risk-service** (`services/risk-service/src/risk_manager.py:71-113`):
   - Remove `inherent_score`, `residual_score` from INSERT column list (GENERATED ALWAYS).
   - Decide: add `target_score` column via migration, or strip from INSERT.
5. **Add schema drift guard**: CI script that diffs each service's SQL column references vs `information_schema.columns`. Fail on mismatch.

### Acceptance
- `POST /pbc/engagements` succeeds end-to-end (we only half-fixed this during QA).
- `POST /audit-planning/engagements` succeeds end-to-end.
- `POST /risk/risks` with `inherent_likelihood`+`inherent_impact` creates a row with auto-computed scores.

---

## Sprint 24 — Infra Wiring Fixes (🟠 HIGH, week 4)

**Goal:** Remove the port mismatches, dependency deadlocks, and stale-image footguns.

### Scope
1. **Port mismatch fixes** in `docker-compose.yml`:
   - `rag-pipeline-service` env refs: `3010` → `3008` (lines 986, 719).
   - `framework-service` env refs: `3012` → `3013` (lines 720, 770, 981, 1033).
   - `pgbouncer:5432` → `pgbouncer:6432` (lines 460, 501).
2. **Break Kafka transitive coupling**:
   - `dashboard-service` depends_on: change `forensic-ml-service`/`rag-pipeline-service` from `service_healthy` → `service_started`, or drop entirely.
3. **Add healthchecks** to: `pgbouncer`, `zookeeper`, `timescaledb`, and any service other services wait on with `service_healthy`.
4. **Flyway migration container** — replace `infra/db/migrate.sh`:
   - Use `flyway/flyway:10-alpine` with `-table=flyway_schema_history`.
   - Remove `|| true` from `start.ps1:146`.
5. **`Makefile`** with `build`, `up`, `down`, `migrate`, `test` targets.
6. **Minimal CI** (`.github/workflows/ci.yml` or equivalent):
   - `docker compose build --pull`
   - Run migrations against an ephemeral Postgres.
   - Run `tests/` pytest suite.

### Acceptance
- `make up` from a clean clone brings every service to healthy without manual `docker compose up -d --no-deps`.
- CI rejects a PR that introduces a schema drift or port mismatch.

---

## Sprint 25 — Prod-Ready Secrets & Network (🟠 HIGH, week 5)

**Goal:** Make the compose stack deployable outside a laptop.

### Scope
1. **`docker-compose.prod.yml` override**:
   - Re-enable `internal: true` on `aegis-internal`.
   - Remove host port bindings for everything except the UIs and the API gateway.
   - No secret defaults — every `${VAR}` must resolve or the stack fails to start.
2. **Move secrets to `.env.prod.example`** (committed) + `.env.prod` (ignored):
   - `POSTGRES_PASSWORD`, `VAULT_ROOT_TOKEN`, `MINIO_ROOT_PASSWORD`, `JWT_SECRET`, `AEGIS_APP_PW`.
3. **Resource limits** on postgres, timescaledb, kafka, minio, mlflow, zk-proof-worker, forensic-ml-service.
4. **Gate dev seeder** behind `SEED_DEMO_DATA=true` — disable in prod override.
5. **Fix `hub-ui` startup race**: add `condition: service_healthy` on its upstreams (auth-service, dashboard-service).

### Acceptance
- `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` validates without any default-string warnings.
- `netstat` on the host shows only UI + gateway ports bound.
- Trying to start without `.env.prod` fails fast with a readable error.

---

## Sprint 26 — Frontend Shared Packages (🟠 HIGH, week 6-7, 2 weeks)

**Goal:** Stop duplicating 1,600+ lines across 13 UIs. Fix the hub-ui prod-breaking URLs.

### Scope
1. **New monorepo packages** under `packages/`:
   - `@via/api-client` — axios factory, tenant header interceptor, global error toast hook.
   - `@via/ui-kit` — `DataTable` (from pbc-ui), `Toaster` (from risk-ui), `ErrorBoundary`, `Modal` (with focus trap + Esc + `role="dialog"` + `aria-modal`), `Layout`.
2. **Replace in all 13 UIs**:
   - Delete `src/api.ts` copies; import from `@via/api-client`.
   - Delete duplicated `ErrorBoundary` (6 copies).
   - Replace modal components with `@via/ui-kit/Modal`.
3. **Fix hub-ui hardcoded localhost**:
   - `hub-ui/src/pages/Dashboard.tsx` (6 refs) and `components/GlobalSearch.tsx:296` — drive from `VITE_MODULE_BASE_URL` + module path.
   - Add `/api` + `/auth` proxy to `hub-ui/vite.config.ts`.
4. **Error surfacing**:
   - Replace `catch { /* fail silently */ }` in `useNotifications.ts:45,73,85` with toast.
   - Wire api-client error interceptor into every UI.
5. **Tenant-header normalization**: single pattern (axios interceptor from risk-ui), single casing (`X-Tenant-ID`).

### Acceptance
- Line count under `services/*-ui/src/api.ts` drops by >80%.
- Playwright test: every UI shows a toast on a forced 500.
- Build `hub-ui` with `VITE_MODULE_BASE_URL=https://via.example.com` — no `localhost` in dist bundle.

---

## Sprint 27 — Accessibility & Modal Remediation (🟡 MEDIUM, week 8)

**Goal:** The 25 modal components become WCAG-compliant.

### Scope
1. Replace every ad-hoc modal div across the 13 UIs with `@via/ui-kit/Modal` (from Sprint 26).
2. Add `aria-sort`, `aria-label`, `role="status"` where missing on dashboards.
3. Ensure severity/status indicators have text + icon, not color only (spot check: `RiskHeatmap.tsx`, `ESGDashboard.tsx`, `SoDMatrix.tsx`).
4. Automated a11y CI: `@axe-core/playwright` on each UI's primary routes.

### Acceptance
- axe-core reports zero serious/critical violations on the smoke-tested routes.

---

## Sprint 28 — Backend Shared Lib & Type Safety (🟡 MEDIUM, week 9)

**Goal:** Stop copy-pasting `tenant_conn` and `Dict[str, Any]`.

### Scope
1. New Python package `services/_shared/audit_common/`:
   - `db.py` — `tenant_conn`, `create_pool`, transaction helpers.
   - `auth.py` — `get_current_user`, JWT validation.
   - `errors.py` — standard HTTPException subclasses.
2. Replace in 10 services: `ai-agent-service`, `audit-planning-service`, `esg-board-service`, `integration-service`, `mobile-sync-service`, `monitoring-service`, `pbc-service`, `risk-service`, `trust-portal-service`, `people-service`.
3. **Replace `Dict[str, Any]` with Pydantic** in the top-8 files: `board_manager.py`, `plan_manager.py`, `risk_manager.py`, `training_manager.py`, `workpaper_manager.py`, `pbc_manager.py`, `monitoring-service/main.py`, `ai-agent-service/main.py`.
4. Fix the 10 uncommented `except Exception: pass` blocks — log with context, re-raise where appropriate (pam-broker and tenant-registry first).

### Acceptance
- `grep -r "async def tenant_conn" services/` returns matches only inside `_shared/`.
- `mypy --strict services/pbc-service/src/pbc_manager.py` passes.

---

## Sprint 29 — Test Coverage & Observability (🟡 MEDIUM, week 10)

**Goal:** Co-locate tests, add baseline coverage for security-critical services.

### Scope
1. Create `tests/` directories inside each of: `auth-service`, `pam-broker`, `tenant-registry`, `pq-crypto-service`, `evidence-store`, `zk-proof-worker`, `forensic-ml-service`.
2. Port relevant sprint-folder tests into service-local tests.
3. Add structured logging (JSON) via `audit_common.logging` — tenant_id + request_id on every log line.
4. CI coverage gate: fail on <60% on security-critical services.

### Acceptance
- Every security-critical service has ≥1 integration test covering its happy path and auth rejection.

---

## Sprint 30 — Cleanup (🟢 LOW, week 11)

**Goal:** Burn-down the low-severity findings.

### Scope
- Delete stray `infra/db/migrations;C` directory.
- Strip `localhost:*` strings from `hub-ui/src/data/tutorials.ts` (template from config).
- Audit dev seeder is gated behind `SEED_DEMO_DATA`.
- Add `ruff --select F401` + `ts-prune` to CI for dead-code detection.
- Document the `DEMO_TENANT_ID` pattern or remove it entirely now that auth is hardened.

### Acceptance
- Repo cleanliness check passes in CI.

---

## Sequencing Notes

- **Sprints 21–23 are non-negotiable before any external deployment.** Each is independently sufficient to cause a breach or P0.
- **Sprint 24 unblocks everything downstream** — without CI + working `make up`, subsequent sprints regress silently.
- **Sprints 25–30 are parallelizable** once 21–24 are done. 26 and 28 can run concurrently (different teams).
- **Total elapsed time**: 11 weeks serial; ~8 weeks with parallelization from Sprint 25 onwards.
