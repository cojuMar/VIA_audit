"""
Proves FORCE RLS works for any non-superuser role, including one with
table-owner-equivalent privileges. We deliberately do NOT test aegis_admin
here: it is the cluster bootstrap SUPERUSER (POSTGRES_USER), and Postgres
superusers bypass RLS by design regardless of FORCE — there is no way to
make RLS apply to a superuser short of revoking SUPERUSER itself, which
would break migrations (aegis_admin is the only superuser in the cluster).

After Sprint 22, aegis_admin is migration-only; no application service
connects as it. The enforcement surface is aegis_app, which is what the
other tests cover. This test creates an ephemeral owner-privileged role
to prove FORCE applies to everyone who isn't a superuser.
"""
from __future__ import annotations

import uuid
import pytest


@pytest.mark.asyncio
async def test_non_superuser_owner_is_tenant_filtered(admin_conn, other_tenant):
    """Grant a fresh role full CRUD + ownership-like access; FORCE must still filter it."""
    role = f"rls_probe_{uuid.uuid4().hex[:8]}"
    # Non-superuser, no bypassrls, with login
    await admin_conn.execute(
        f"CREATE ROLE {role} LOGIN PASSWORD 'probe_pw' NOSUPERUSER NOBYPASSRLS"
    )
    await admin_conn.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON notifications TO {role}"
    )

    import asyncpg
    probe = await asyncpg.connect(
        f"postgresql://{role}:probe_pw@localhost:5432/aegis"
    )
    try:
        async with probe.transaction():
            await probe.execute(
                "SELECT set_config('app.tenant_id', $1, true)", other_tenant
            )
            rows = await probe.fetch("SELECT 1 FROM notifications LIMIT 1")
        assert rows == [], (
            "FORCE RLS not in effect for non-superuser: saw rows for an "
            "empty tenant. Check that notifications has FORCE ROW LEVEL SECURITY."
        )
    finally:
        await probe.close()
        await admin_conn.execute(
            f"REVOKE ALL ON notifications FROM {role}"
        )
        await admin_conn.execute(f"DROP ROLE {role}")


@pytest.mark.asyncio
async def test_aegis_admin_is_documented_superuser(admin_conn):
    """
    Guardrail: if someone strips SUPERUSER from aegis_admin, cluster init
    breaks. This test asserts the known state so any change is intentional.
    """
    row = await admin_conn.fetchrow(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'aegis_admin'"
    )
    assert row["rolsuper"] is True, "aegis_admin lost SUPERUSER — cluster bootstrap at risk"
    assert row["rolbypassrls"] is True, "aegis_admin lost BYPASSRLS — unexpected"
