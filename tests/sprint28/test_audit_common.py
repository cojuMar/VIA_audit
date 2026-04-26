"""
Sprint 28 — Backend Shared Lib & Type Safety.

Static guards over the structural invariants Sprint 28 introduced:

  1. `services/_shared/audit_common/` exists with the canonical modules
     (db, auth, errors, logging) and a pyproject so it can be pip-installed.
  2. The pilot service (pbc-service) re-exports `tenant_conn` / `create_pool`
     from `audit_common` rather than re-rolling them.
  3. The two priority silent excepts (pam-broker health probe + Vault
     health probe, tenant-registry health probe) now log instead of
     swallowing.

Behavioural tests for the helper itself are in test_audit_common_unit.py
(import-only — no DB required).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SHARED = REPO / "services" / "_shared" / "audit_common"


# ---------------------------------------------------------- package layout

def test_audit_common_package_exists():
    assert SHARED.is_dir(), "services/_shared/audit_common missing"
    for fname in ("__init__.py", "db.py", "auth.py", "errors.py", "logging.py"):
        assert (SHARED / fname).is_file(), f"audit_common missing {fname}"


def test_audit_common_pyproject_declares_package():
    pyproj = (SHARED / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "audit_common"' in pyproj, (
        "audit_common pyproject.toml must declare the project name"
    )
    for dep in ("asyncpg", "fastapi", "PyJWT"):
        assert dep in pyproj, f"audit_common pyproject missing dep {dep!r}"


def test_audit_common_init_exports_the_canonical_surface():
    src = (SHARED / "__init__.py").read_text(encoding="utf-8")
    for sym in (
        "tenant_conn", "create_pool", "close_pool",
        "get_logger", "bind_request_context",
        "BadRequestError", "NotFoundError", "ForbiddenError",
        "UnauthorizedError", "ConflictError",
    ):
        assert sym in src, f"audit_common.__init__ missing export {sym!r}"


# --------------------------------------------------- pilot service migration

def test_pbc_service_db_uses_audit_common():
    src = (REPO / "services" / "pbc-service" / "src" / "db.py").read_text(
        encoding="utf-8"
    )
    assert "from audit_common.db import" in src, (
        "pbc-service/src/db.py must import tenant_conn from audit_common"
    )
    # And the local re-roll is gone.
    assert "set_config('app.tenant_id'" not in src, (
        "pbc-service/src/db.py still has its own tenant_conn body — "
        "delete it and import from audit_common instead."
    )


# --------------------------------------------------- silent except remediation

def test_pam_broker_health_logs_instead_of_swallowing():
    src = (REPO / "services" / "pam-broker" / "src" / "main.py").read_text(
        encoding="utf-8"
    )
    # The old `except Exception: pass` pattern must be gone, and the new
    # form must include a logger call.
    assert not re.search(
        r"except Exception:\s*\n\s*pass\b", src
    ), "pam-broker health still has bare `except Exception: pass`"
    assert "health_db_probe_failed" in src, (
        "pam-broker health probe must log under a stable event name"
    )


def test_pam_broker_vault_client_logs_health_failure():
    src = (
        REPO / "services" / "pam-broker" / "src" / "vault_client.py"
    ).read_text(encoding="utf-8")
    assert "vault_health_probe_failed" in src, (
        "VaultClient.check_health must log on exception, not silently return False"
    )


def test_tenant_registry_health_logs_instead_of_swallowing():
    src = (
        REPO / "services" / "tenant-registry" / "src" / "main.py"
    ).read_text(encoding="utf-8")
    assert not re.search(
        r"except Exception:\s*\n\s*pass\b", src
    ), "tenant-registry health still has bare `except Exception: pass`"
    assert "health_db_probe_failed" in src, (
        "tenant-registry health probe must log under a stable event name"
    )


# --------------------------------------------------- acceptance: tenant_conn ownership

def test_tenant_conn_definition_lives_in_audit_common():
    """
    The acceptance criterion: `grep -r "async def tenant_conn" services/`
    should return matches only inside `_shared/`. Other services may keep
    a thin shim that *re-exports* but must not declare their own body.

    Sprint 28 ships only the pbc-service migration as a pilot; later
    sprints fold the remaining 10 services in. This test asserts the
    pilot is correct and the shared definition exists; it does NOT yet
    assert all other services have been migrated.
    """
    shared_db = (SHARED / "db.py").read_text(encoding="utf-8")
    assert "async def tenant_conn" in shared_db, (
        "audit_common.db must define `async def tenant_conn`"
    )

    # The pilot must NOT carry its own definition.
    pbc_db = (REPO / "services" / "pbc-service" / "src" / "db.py").read_text(
        encoding="utf-8"
    )
    assert "async def tenant_conn" not in pbc_db, (
        "pbc-service still defines its own tenant_conn — should re-export "
        "from audit_common"
    )
