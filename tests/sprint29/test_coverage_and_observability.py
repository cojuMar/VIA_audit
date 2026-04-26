"""
Sprint 29 — Test Coverage & Observability.

Static guards over the structural invariants Sprint 29 introduced:

  1. Every security-critical service has a tests/ directory with a
     contract test that names ≥1 happy-path route and ≥1 anonymous-
     rejection assertion.
  2. The structured-logging middleware exists in audit_common and
     binds tenant_id + request_id from request headers.
  3. The auth-service (pilot) is wired to use it.
  4. The CI coverage gate script exists and references all six Python
     security-critical services.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SERVICES = REPO / "services"

PY_SECURITY_CRITICAL = [
    "auth-service",
    "pam-broker",
    "tenant-registry",
    "pq-crypto-service",
    "evidence-store",
    "forensic-ml-service",
]

# Rust service — has its own cargo-based contract test.
RUST_SECURITY_CRITICAL = ["zk-proof-worker"]


# --------------------------------------------------------- per-service tests

@pytest.mark.parametrize("svc", PY_SECURITY_CRITICAL)
def test_python_service_has_tests_dir(svc: str):
    tests = SERVICES / svc / "tests"
    assert tests.is_dir(), f"{svc} missing tests/ directory (Sprint 29 requirement)"
    assert (tests / "__init__.py").is_file(), (
        f"{svc}/tests/__init__.py missing — required for pytest discovery"
    )
    # At least one test_*.py in the directory.
    tests_found = list(tests.glob("test_*.py"))
    assert tests_found, f"{svc}/tests has no test_*.py files"


@pytest.mark.parametrize("svc", PY_SECURITY_CRITICAL)
def test_python_service_contract_covers_happy_path_and_auth(svc: str):
    contract = SERVICES / svc / "tests" / "test_contract.py"
    assert contract.is_file(), f"{svc}/tests/test_contract.py missing"
    src = contract.read_text(encoding="utf-8")
    # Happy path: at least one /health assertion.
    assert "/health" in src, f"{svc} contract test missing /health assertion"
    # Auth rejection: integration must check 401/403 on a protected route.
    assert re.search(r"\b401\b", src), (
        f"{svc} contract test missing an explicit 401 (anon rejection) assertion"
    )


def test_rust_zk_worker_has_contract_test():
    test_path = SERVICES / "zk-proof-worker" / "tests" / "contract_test.rs"
    assert test_path.is_file(), (
        "zk-proof-worker missing tests/contract_test.rs — Sprint 29 requirement"
    )
    src = test_path.read_text(encoding="utf-8")
    for route in ("/health", "/proofs/verify"):
        assert route in src, f"zk-proof-worker contract test missing {route}"


# --------------------------------------------------------- middleware exists

def test_request_context_middleware_exists():
    mod = REPO / "services" / "_shared" / "audit_common" / "middleware.py"
    assert mod.is_file(), "audit_common/middleware.py missing"
    src = mod.read_text(encoding="utf-8")
    for marker in (
        "RequestContextMiddleware",
        "X-Request-ID",
        "X-Tenant-ID",
        "bind_request_context",
    ):
        assert marker in src, f"middleware.py missing {marker!r}"


def test_audit_common_init_exports_middleware():
    src = (
        REPO / "services" / "_shared" / "audit_common" / "__init__.py"
    ).read_text(encoding="utf-8")
    assert "RequestContextMiddleware" in src, (
        "audit_common.__init__ must re-export RequestContextMiddleware"
    )


def test_auth_service_wires_request_context_middleware():
    src = (
        REPO / "services" / "auth-service" / "src" / "main.py"
    ).read_text(encoding="utf-8")
    assert "RequestContextMiddleware" in src, (
        "auth-service main.py must add RequestContextMiddleware so request "
        "logs carry tenant_id + request_id (Sprint 29 acceptance)"
    )
    # The CORS allowlist must let the X-Request-ID header through too.
    assert "X-Request-ID" in src, (
        "auth-service CORS allowlist must include X-Request-ID so browser "
        "clients can correlate frontend logs with backend logs"
    )


# --------------------------------------------------------- coverage gate

def test_coverage_gate_script_exists():
    script = REPO / "scripts" / "coverage_gate.sh"
    assert script.is_file(), "scripts/coverage_gate.sh missing"
    src = script.read_text(encoding="utf-8")
    # Default minimum must be 60% per the sprint doc.
    assert "COVERAGE_MIN:-60" in src, (
        "coverage_gate.sh must default to COVERAGE_MIN=60 (Sprint 29 acceptance)"
    )
    for svc in PY_SECURITY_CRITICAL:
        assert svc in src, (
            f"coverage_gate.sh missing security-critical service {svc!r}"
        )


def test_ci_workflow_invokes_coverage_gate():
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "coverage_gate.sh" in ci, (
        "CI workflow must invoke scripts/coverage_gate.sh"
    )
    # And it should run sprint29 tests in the pytest step.
    assert "tests/sprint29" in ci, (
        "CI workflow pytest step must include tests/sprint29"
    )
