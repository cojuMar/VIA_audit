# Sprint 22 — RLS Actually Works

Regression suite for the RLS hardening in Sprint 22.

| File | What it proves |
|------|---------------|
| `test_rls_force_enforced.py` | Every RLS-enabled table has `FORCE ROW LEVEL SECURITY` — owners cannot bypass. |
| `test_rls_policy_coverage.py` | Every RLS-enabled table has at least one policy. Any table with a `tenant_id` column also has RLS. |
| `test_aegis_app_tenant_isolation.py` | Connected as `aegis_app` with `app.tenant_id = A`, `SELECT` from a tenant table returns ONLY A's rows. |
| `test_aegis_admin_no_bypass.py` | Same as above but connecting as `aegis_admin` — FORCE RLS means even the owner is filtered. |
| `test_pgbouncer_no_tenant_leak.py` | After a transaction sets `app.tenant_id = A`, a later unrelated transaction on the same pool sees no residual setting. |
| `test_set_config_uses_true.py` | No service source contains `set_config('app.tenant_id', $1, false)` — all call sites are transaction-scoped. |

## Running

```bash
export DATABASE_URL=postgresql://aegis_admin:aegis_dev_pw@localhost:5432/aegis
export DATABASE_URL_APP=postgresql://aegis_app:aegis_app_dev_pw@localhost:5432/aegis
pip install pytest pytest-asyncio asyncpg
pytest tests/sprint22 -v
```
