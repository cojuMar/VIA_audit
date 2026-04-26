"""
Pre-Sprint-21 bug: JWT_SECRET defaulted to a hardcoded string if the env var
was unset. Any deployment that forgot to set it would use a publicly-known
secret — all JWTs forgeable.

Post-Sprint-21 contract: with ENV=prod and no JWT_SECRET, the service must
exit non-zero during import.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap


def test_prod_without_jwt_secret_fails_to_start():
    """
    Import the auth-service module with ENV=prod and no JWT_SECRET.
    The module-level guard must call sys.exit(1).
    """
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    svc_src = os.path.join(repo_root, "services", "auth-service", "src")

    if not os.path.isdir(svc_src):
        # Test was invoked outside the repo — skip rather than fail.
        import pytest
        pytest.skip("auth-service source not found")

    code = textwrap.dedent(
        f"""
        import os, sys
        os.environ["ENV"] = "prod"
        os.environ.pop("JWT_SECRET", None)
        sys.path.insert(0, {svc_src!r})
        try:
            import main  # noqa: F401
        except SystemExit as e:
            print("EXITED:", e.code)
            sys.exit(int(e.code) if e.code else 0)
        print("NO_EXIT")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0, (
        f"auth-service started in prod without JWT_SECRET (stdout={result.stdout!r})"
    )
    assert "EXITED: 1" in result.stdout or "JWT_SECRET" in result.stderr
