"""
Sprint 27 — Accessibility & Modal Remediation.

Static lint-style tests asserting the structural a11y invariants Sprint 27
introduced. The behavioural acceptance ("axe reports zero serious/critical
violations") runs through `npm run test:a11y` against the live stack — see
tests/a11y/axe.spec.mjs and playwright.config.ts.

These Python tests guard the source-level patterns so a refactor can't
silently strip them.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


# --------------------------------------------------------- spot-check files

DASHBOARD_HEATMAP = (
    REPO / "services" / "dashboard-ui" / "src" / "components" / "RiskHeatmap.tsx"
)
SOD_MATRIX = (
    REPO / "services" / "monitoring-ui" / "src" / "components" / "SoDMatrix.tsx"
)
ESG_DASHBOARD = (
    REPO / "services" / "esg-board-ui" / "src" / "components" / "ESGDashboard.tsx"
)
NDA_MODAL = (
    REPO / "services" / "trust-portal-ui" / "src" / "components" / "NDASigningModal.tsx"
)


# -------------------------------------- text-or-icon (not color-only) checks

def test_dashboard_riskheatmap_cells_carry_severity_text():
    """
    Each cell must communicate severity by text + color, not color alone.
    Sprint 27 added a `riskBand` label (Critical/High/Medium/Low/Minimal)
    that prints in every cell and is announced by screen readers via
    aria-label.
    """
    src = DASHBOARD_HEATMAP.read_text(encoding="utf-8")
    assert "riskBand" in src, (
        "RiskHeatmap missing riskBand() helper that turns avg_risk into a "
        "categorical severity label (text, not just color)."
    )
    assert "aria-label=" in src, (
        "RiskHeatmap cells must carry aria-label so the severity is "
        "available to screen-readers, not just sighted users."
    )


def test_dashboard_riskheatmap_table_is_labelled():
    src = DASHBOARD_HEATMAP.read_text(encoding="utf-8")
    assert 'aria-label="Risk heatmap' in src, (
        "RiskHeatmap <table> must carry an aria-label describing what it shows."
    )
    assert 'scope="col"' in src, (
        "RiskHeatmap headers must declare scope=col for screen-reader column navigation."
    )


def test_sod_matrix_cells_have_aria_label():
    """SoDMatrix cells encode severity by colour + a single letter (C/H/M/L);
    Sprint 27 added an aria-label so the full word is announced."""
    src = SOD_MATRIX.read_text(encoding="utf-8")
    assert "aria-label=" in src, (
        "SoDMatrix cells must carry aria-label describing the severity."
    )
    assert "severity violation" in src, (
        "SoDMatrix violation cells must announce the severity word, not just a letter."
    )


def test_esg_dashboard_progressbar_has_aria():
    src = ESG_DASHBOARD.read_text(encoding="utf-8")
    assert 'role="progressbar"' in src, (
        "ESGDashboard overall-coverage bar must have role=progressbar"
    )
    assert "aria-valuenow=" in src, (
        "ESGDashboard progressbar must report aria-valuenow"
    )


# ------------------------------------------------------- modal a11y invariants

def test_nda_modal_meets_dialog_pattern():
    src = NDA_MODAL.read_text(encoding="utf-8")
    for marker in (
        'role="dialog"',
        'aria-modal="true"',
        "aria-labelledby=",
        "Escape",
    ):
        assert marker in src, (
            f"NDASigningModal missing {marker!r} — required for the WCAG dialog pattern."
        )
    # Focus restoration and trap (mirrors @via/ui-kit/Modal).
    assert "previouslyFocused" in src, (
        "NDASigningModal must restore focus to the opener on close."
    )


def test_via_ui_kit_modal_remains_dialog_compliant():
    """Sprint 26 shipped the canonical Modal; Sprint 27 depends on it."""
    src = (REPO / "packages" / "ui-kit" / "src" / "Modal.tsx").read_text(encoding="utf-8")
    for marker in ('role="dialog"', 'aria-modal="true"', "aria-labelledby", "Escape"):
        assert marker in src, f"@via/ui-kit/Modal lost {marker!r}"


# ------------------------------------------------------- a11y harness presence

def test_axe_playwright_harness_exists():
    assert (REPO / "tests" / "a11y" / "axe.spec.mjs").exists(), (
        "Sprint 27 axe-core/playwright harness missing"
    )
    assert (REPO / "playwright.config.ts").exists(), (
        "playwright.config.ts missing — required to drive the a11y harness"
    )


def test_axe_harness_covers_every_ui():
    """Every UI listed in services/ must appear in the smoke harness."""
    spec = (REPO / "tests" / "a11y" / "axe.spec.mjs").read_text(encoding="utf-8")
    ui_dirs = sorted(
        p.name for p in (REPO / "services").iterdir()
        if p.is_dir() and p.name.endswith("-ui")
    )
    missing = [ui for ui in ui_dirs if ui not in spec]
    assert missing == [], (
        f"axe harness does not reference these UIs: {missing}. "
        "Add them to the ROUTES list in tests/a11y/axe.spec.mjs."
    )


def test_root_package_json_declares_axe_test_script():
    pkg = json.loads((REPO / "package.json").read_text(encoding="utf-8"))
    scripts = pkg.get("scripts") or {}
    assert "test:a11y" in scripts, (
        "package.json missing 'test:a11y' script — `npm run test:a11y` "
        "must drive the axe harness."
    )
    devdeps = pkg.get("devDependencies") or {}
    for dep in ("@axe-core/playwright", "@playwright/test"):
        assert dep in devdeps, f"package.json devDependencies missing {dep}"
