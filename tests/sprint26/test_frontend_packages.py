"""
Sprint 26 — Frontend Shared Packages.

These tests are intentionally static / lint-style. They guard the
structural invariants that Sprint 26 introduced:

  1. The `packages/api-client` and `packages/ui-kit` workspaces exist
     with the canonical exports the rest of the stack will import.
  2. The root npm workspace declaration includes `packages/*`.
  3. hub-ui no longer hardcodes `http://localhost:<port>` — every cross-
     module URL is built from `VITE_MODULE_BASE_URL` (with a dev fallback
     that lives in exactly one helper file).
  4. hub-ui's vite.config.ts proxies `/api` and `/auth` so the dev server
     can talk to the auth-service and aggregators without CORS gymnastics.
  5. The "fail silently" silent-catch anti-pattern is gone from the
     hub-ui code paths Sprint 26 touched (Sprint 27 finishes the rest).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- workspaces

def test_root_package_json_declares_packages_workspace():
    pkg = json.loads((REPO / "package.json").read_text(encoding="utf-8"))
    workspaces = pkg.get("workspaces") or []
    assert "packages/*" in workspaces, (
        f"root package.json must declare 'packages/*' as a workspace; "
        f"got {workspaces!r}"
    )


def test_api_client_package_exists_with_canonical_exports():
    p = REPO / "packages" / "api-client"
    pkg = json.loads((p / "package.json").read_text(encoding="utf-8"))
    assert pkg["name"] == "@via/api-client"
    src = (p / "src" / "index.ts").read_text(encoding="utf-8")
    for symbol in ("createApiClient", "setTenantId", "getTenantId"):
        assert symbol in src, f"@via/api-client missing export {symbol!r}"
    # The canonical tenant-header casing.
    assert "X-Tenant-ID" in src, (
        "@via/api-client must default to 'X-Tenant-ID' header casing"
    )


def test_ui_kit_package_exists_with_canonical_exports():
    p = REPO / "packages" / "ui-kit"
    pkg = json.loads((p / "package.json").read_text(encoding="utf-8"))
    assert pkg["name"] == "@via/ui-kit"
    idx = (p / "src" / "index.ts").read_text(encoding="utf-8")
    for symbol in (
        "Modal", "ToasterProvider", "useToast",
        "ErrorBoundary", "DataTable", "Layout",
    ):
        assert symbol in idx, f"@via/ui-kit missing export {symbol!r}"


def test_modal_uses_dialog_role_and_aria_modal():
    """Sprint 26 Modal must satisfy the WCAG dialog pattern out of the box."""
    src = (REPO / "packages" / "ui-kit" / "src" / "Modal.tsx").read_text(
        encoding="utf-8"
    )
    assert 'role="dialog"' in src, "Modal missing role=\"dialog\""
    assert 'aria-modal="true"' in src, "Modal missing aria-modal=\"true\""
    assert "aria-labelledby" in src, "Modal missing aria-labelledby"
    assert "Escape" in src, "Modal must close on Escape"


# ---------------------------------------------------------------- hub-ui URLs

HUB_DASHBOARD = REPO / "services" / "hub-ui" / "src" / "pages" / "Dashboard.tsx"
HUB_GLOBAL_SEARCH = (
    REPO / "services" / "hub-ui" / "src" / "components" / "GlobalSearch.tsx"
)
HUB_MODULE_URL = REPO / "services" / "hub-ui" / "src" / "data" / "moduleUrl.ts"


def test_hub_ui_module_url_helper_exists():
    assert HUB_MODULE_URL.exists(), (
        "hub-ui must have a single moduleUrl.ts helper that owns the "
        "VITE_MODULE_BASE_URL → module URL mapping"
    )
    src = HUB_MODULE_URL.read_text(encoding="utf-8")
    assert "VITE_MODULE_BASE_URL" in src, (
        "moduleUrl.ts must read VITE_MODULE_BASE_URL"
    )


def test_hub_ui_no_hardcoded_localhost_module_urls_in_dashboard():
    """
    Dashboard.tsx must not bake `http://localhost:<port>` into call sites
    that ship to prod. The single allowed dev fallback lives in
    moduleUrl.ts.
    """
    src = HUB_DASHBOARD.read_text(encoding="utf-8")
    offenders = re.findall(r"http://localhost:\d+", src)
    assert offenders == [], (
        f"Dashboard.tsx still has hardcoded localhost URLs: {offenders}. "
        "Route through moduleUrl()/moduleUrlById() instead."
    )


def test_hub_ui_no_hardcoded_localhost_module_urls_in_global_search():
    src = HUB_GLOBAL_SEARCH.read_text(encoding="utf-8")
    offenders = re.findall(r"http://localhost:\d+", src)
    assert offenders == [], (
        f"GlobalSearch.tsx still has hardcoded localhost URLs: {offenders}. "
        "Route through moduleUrl() instead."
    )


# ---------------------------------------------------------------- vite proxy

def test_hub_ui_vite_config_proxies_api_and_auth():
    src = (REPO / "services" / "hub-ui" / "vite.config.ts").read_text(
        encoding="utf-8"
    )
    assert "'/auth'" in src or '"/auth"' in src, (
        "hub-ui vite.config.ts must proxy /auth"
    )
    assert "'/api'" in src or '"/api"' in src, (
        "hub-ui vite.config.ts must proxy /api"
    )


# ----------------------------------------------------------- silent catches

def test_use_notifications_no_silent_catches():
    src = (
        REPO / "services" / "hub-ui" / "src" / "hooks" / "useNotifications.ts"
    ).read_text(encoding="utf-8")
    assert "fail silently" not in src.lower(), (
        "useNotifications.ts still contains a `fail silently` swallow. "
        "Surface via console.warn or the @via/ui-kit toaster."
    )
    # An empty `catch { }` block (with optional whitespace) is the smoking gun.
    assert not re.search(r"catch\s*\{\s*\}", src), (
        "useNotifications.ts has an empty catch block — never swallow errors."
    )


def test_global_search_no_silent_catch():
    src = HUB_GLOBAL_SEARCH.read_text(encoding="utf-8")
    assert "fail silently" not in src.lower(), (
        "GlobalSearch.tsx still contains a `fail silently` swallow."
    )
    assert not re.search(r"catch\s*\{\s*\}", src), (
        "GlobalSearch.tsx has an empty catch block — never swallow errors."
    )
