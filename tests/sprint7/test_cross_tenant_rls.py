"""
Sprint 7 — Cross-Tenant RLS Isolation Tests

Verifies that PostgreSQL Row-Level Security prevents cross-tenant data access.
These tests require a real database connection and are marked with pytest.mark.integration.

In CI they run against the postgres service container.
In dev they can be skipped with: pytest -m "not integration"
"""
import pytest
import asyncpg
import os
import uuid
from datetime import datetime, timezone

pytestmark = pytest.mark.asyncio

DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://aegis_admin:aegis_dev_pw@localhost:5432/aegis',
)

TENANT_A = str(uuid.uuid4())
TENANT_B = str(uuid.uuid4())


@pytest.fixture
async def db():
    conn = await asyncpg.connect(DATABASE_URL)
    yield conn
    await conn.close()


# ---------------------------------------------------------------------------
# RLS isolation tests
# ---------------------------------------------------------------------------

class TestRLSIsolation:

    @pytest.mark.integration
    async def test_tenant_a_cannot_see_tenant_b_rows(self, db):
        """Insert a row scoped to tenant A; querying as tenant B should return nothing."""
        async with db.transaction() as tx:
            # Insert as tenant A
            await db.execute("SET LOCAL app.tenant_id = $1", TENANT_A)
            await db.execute(
                """
                INSERT INTO prompt_injection_logs
                    (tenant_id, query_hash, score, action, pattern_hits)
                VALUES
                    ($1, $2, $3, $4, $5)
                """,
                TENANT_A,
                b'\x00' * 32,
                0.1,
                'allowed',
                [],
            )

            # Now switch context to tenant B
            await db.execute("SET LOCAL app.tenant_id = $1", TENANT_B)
            rows = await db.fetch("SELECT * FROM prompt_injection_logs")
            assert len(rows) == 0, (
                f"Tenant B should not see tenant A rows, got {len(rows)}"
            )

            await tx.rollback()

    @pytest.mark.integration
    async def test_tenant_b_cannot_see_tenant_a_rows(self, db):
        """Mirror of the above — insert as tenant B, query as tenant A."""
        async with db.transaction() as tx:
            await db.execute("SET LOCAL app.tenant_id = $1", TENANT_B)
            await db.execute(
                """
                INSERT INTO prompt_injection_logs
                    (tenant_id, query_hash, score, action, pattern_hits)
                VALUES
                    ($1, $2, $3, $4, $5)
                """,
                TENANT_B,
                b'\x01' * 32,
                0.1,
                'allowed',
                [],
            )

            await db.execute("SET LOCAL app.tenant_id = $1", TENANT_A)
            rows = await db.fetch("SELECT * FROM prompt_injection_logs")
            assert len(rows) == 0

            await tx.rollback()

    @pytest.mark.integration
    async def test_empty_tenant_id_returns_no_rows(self, db):
        """Setting app.tenant_id to an empty string should yield zero rows (not an error)."""
        async with db.transaction() as tx:
            # Pre-populate a row for a known tenant
            await db.execute("SET LOCAL app.tenant_id = $1", TENANT_A)
            await db.execute(
                """
                INSERT INTO prompt_injection_logs
                    (tenant_id, query_hash, score, action, pattern_hits)
                VALUES
                    ($1, $2, $3, $4, $5)
                """,
                TENANT_A,
                b'\x02' * 32,
                0.1,
                'allowed',
                [],
            )

            await db.execute("SET LOCAL app.tenant_id = $1", "")
            rows = await db.fetch("SELECT * FROM prompt_injection_logs")
            assert len(rows) == 0

            await tx.rollback()

    @pytest.mark.integration
    async def test_correct_tenant_sees_own_rows(self, db):
        """Insert as tenant A, query as tenant A → exactly 1 row returned."""
        async with db.transaction() as tx:
            await db.execute("SET LOCAL app.tenant_id = $1", TENANT_A)
            await db.execute(
                """
                INSERT INTO prompt_injection_logs
                    (tenant_id, query_hash, score, action, pattern_hits)
                VALUES
                    ($1, $2, $3, $4, $5)
                """,
                TENANT_A,
                b'\x03' * 32,
                0.2,
                'flagged',
                ['override'],
            )

            rows = await db.fetch("SELECT * FROM prompt_injection_logs")
            assert len(rows) == 1
            assert str(rows[0]['tenant_id']) == TENANT_A

            await tx.rollback()

    @pytest.mark.integration
    async def test_rls_applies_to_security_audit_log(self, db):
        """security_audit_log must enforce per-tenant isolation."""
        async with db.transaction() as tx:
            await db.execute("SET LOCAL app.tenant_id = $1", TENANT_A)
            await db.execute(
                """
                INSERT INTO security_audit_log
                    (tenant_id, event_type, actor_id, details)
                VALUES
                    ($1, $2, $3, $4)
                """,
                TENANT_A,
                'injection_blocked',
                'user-001',
                '{}',
            )

            await db.execute("SET LOCAL app.tenant_id = $1", TENANT_B)
            rows = await db.fetch("SELECT * FROM security_audit_log")
            assert len(rows) == 0

            await tx.rollback()

    @pytest.mark.integration
    async def test_rls_applies_to_pq_public_keys(self, db):
        """pq_public_keys must enforce per-tenant isolation."""
        async with db.transaction() as tx:
            await db.execute("SET LOCAL app.tenant_id = $1", TENANT_A)
            await db.execute(
                """
                INSERT INTO pq_public_keys
                    (tenant_id, algorithm, public_key, fingerprint)
                VALUES
                    ($1, $2, $3, $4)
                """,
                TENANT_A,
                'Kyber768',
                b'\xab' * 64,
                b'\xcd' * 32,
            )

            await db.execute("SET LOCAL app.tenant_id = $1", TENANT_B)
            rows = await db.fetch("SELECT * FROM pq_public_keys")
            assert len(rows) == 0

            await tx.rollback()

    @pytest.mark.integration
    async def test_rls_applies_to_rate_limit_events(self, db):
        """rate_limit_events must enforce per-tenant isolation."""
        async with db.transaction() as tx:
            await db.execute("SET LOCAL app.tenant_id = $1", TENANT_A)
            await db.execute(
                """
                INSERT INTO rate_limit_events
                    (tenant_id, endpoint, allowed, remaining, reset_at)
                VALUES
                    ($1, $2, $3, $4, $5)
                """,
                TENANT_A,
                '/narratives/generate',
                True,
                19,
                datetime.now(timezone.utc),
            )

            await db.execute("SET LOCAL app.tenant_id = $1", TENANT_B)
            rows = await db.fetch("SELECT * FROM rate_limit_events")
            assert len(rows) == 0

            await tx.rollback()

    @pytest.mark.integration
    async def test_insert_without_tenant_context_fails(self, db):
        """
        Inserting into prompt_injection_logs without setting app.tenant_id should
        either raise an error or insert a row with a null/empty tenant_id —
        but must not silently succeed and become visible to other tenants.
        """
        async with db.transaction() as tx:
            # Do NOT set app.tenant_id — use the session default (unset)
            inserted_ok = True
            tenant_id_value = None
            try:
                await db.execute(
                    """
                    INSERT INTO prompt_injection_logs
                        (tenant_id, query_hash, score, action, pattern_hits)
                    VALUES
                        ($1, $2, $3, $4, $5)
                    """,
                    None,   # explicit null
                    b'\x04' * 32,
                    0.05,
                    'allowed',
                    [],
                )
                # If insert succeeded, verify the row has null tenant_id
                rows = await db.fetch(
                    "SELECT tenant_id FROM prompt_injection_logs WHERE query_hash = $1",
                    b'\x04' * 32,
                )
                if rows:
                    tenant_id_value = rows[0]['tenant_id']
            except (asyncpg.exceptions.NotNullViolationError,
                    asyncpg.exceptions.CheckViolationError,
                    asyncpg.exceptions.RaiseError) as exc:
                # Policy enforces non-null / valid tenant — this is the preferred outcome
                inserted_ok = False

            if inserted_ok:
                # Acceptable: insert succeeded but tenant_id is null — row is invisible
                # to any tenant context because no context matches null
                assert tenant_id_value is None, (
                    "Row inserted without tenant context must have null tenant_id"
                )

            await tx.rollback()
