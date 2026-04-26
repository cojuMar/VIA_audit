# Sprint 21 — Auth Hardening Regression Tests

Covers every CVE-class bug fixed in Sprint 21:

| File | Attack / Defence |
|------|------------------|
| `test_register_role_elevation.py` | Anonymous `POST /auth/register` with `role: "super_admin"` — must NOT produce a super_admin JWT. |
| `test_notifications_require_auth.py` | `GET/POST/PATCH/DELETE /auth/notifications*` — must return 401 without a JWT; must use JWT's `tenant_id`, not body/query. |
| `test_search_requires_auth.py` | `POST /auth/search` — must return 401 without a JWT; must ignore body `tenant_id`. |
| `test_tenant_id_injection.py` | `tenant_id` field with SQL payload — must not execute as SQL (parameterised set_config). |
| `test_cors_no_wildcard.py` | `app.user_middleware` must not contain `allow_origins=["*"]`. |
| `test_jwt_secret_required.py` | Starting app with `ENV=prod` and no `JWT_SECRET` must exit non-zero. |

## How to run

These tests hit a running auth-service. From repo root:

```bash
# Start the stack with dev defaults
docker compose up -d auth-service postgres

# Install test deps
pip install httpx pytest pytest-asyncio

# Run
pytest tests/sprint21/ -v
```

The `AUTH_BASE_URL` env var overrides the default `http://localhost:3010`.
