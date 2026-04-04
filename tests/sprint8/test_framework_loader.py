import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/framework-service'))

import pytest
import yaml
import tempfile
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.framework_loader import FrameworkLoader


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

FRAMEWORKS_DIR = os.path.join(os.path.dirname(__file__), '../../frameworks')

_HAS_FRAMEWORKS_DIR = os.path.isdir(FRAMEWORKS_DIR)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pool():
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=str(__import__('uuid').uuid4()))
    conn.execute = AsyncMock(return_value=None)

    tx_ctx = MagicMock()
    tx_ctx.__aenter__ = AsyncMock(return_value=None)
    tx_ctx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx_ctx)

    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


def _minimal_framework_yaml(slug: str, num_controls: int = 12) -> dict:
    controls = []
    for i in range(1, num_controls + 1):
        controls.append({
            "id": f"{slug.upper()[:2]}{i}.1",
            "domain": "Test Domain",
            "title": f"Control {i}",
            "description": f"Description for control {i}.",
            "evidence_types": ["policy_document"],
            "testing_frequency": "annual",
            "is_key_control": i <= 3,
        })
    return {
        "slug": slug,
        "name": f"Test Framework {slug}",
        "version": "1.0",
        "category": "security",
        "issuing_body": "TestBody",
        "description": f"Test framework {slug}",
        "metadata": {},
        "domains": [{"name": "Test Domain", "prefix": slug.upper()[:2]}],
        "controls": controls,
    }


def _write_yaml(directory: str, filename: str, data: dict) -> Path:
    path = Path(directory) / filename
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
    return path


# ---------------------------------------------------------------------------
# TestFrameworkLoader
# ---------------------------------------------------------------------------

class TestFrameworkLoader:

    @pytest.mark.skipif(not _HAS_FRAMEWORKS_DIR, reason="frameworks/ dir not present")
    def test_load_soc2_yaml_if_exists(self):
        soc2_path = os.path.join(FRAMEWORKS_DIR, "soc2-type2.yaml")
        if not os.path.isfile(soc2_path):
            pytest.skip("soc2-type2.yaml not found")

        with open(soc2_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        assert "controls" in data, "soc2-type2.yaml must have a 'controls' key"
        assert len(data["controls"]) >= 20, (
            f"Expected >= 20 controls in soc2-type2.yaml, found {len(data['controls'])}"
        )

    @pytest.mark.skipif(not _HAS_FRAMEWORKS_DIR, reason="frameworks/ dir not present")
    def test_framework_slug_matches_filename(self):
        yaml_files = list(Path(FRAMEWORKS_DIR).glob("*.yaml"))
        assert yaml_files, "No YAML files found in frameworks/"

        for path in yaml_files:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            expected_slug = path.stem
            assert data.get("slug") == expected_slug, (
                f"File '{path.name}': expected slug='{expected_slug}', got slug='{data.get('slug')}'"
            )

    @pytest.mark.skipif(not _HAS_FRAMEWORKS_DIR, reason="frameworks/ dir not present")
    def test_all_controls_have_required_fields(self):
        required_fields = {"id", "domain", "title", "description", "evidence_types",
                           "testing_frequency", "is_key_control"}
        yaml_files = list(Path(FRAMEWORKS_DIR).glob("*.yaml"))
        assert yaml_files, "No YAML files found in frameworks/"

        for path in yaml_files:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            for ctrl in data.get("controls", []):
                missing = required_fields - set(ctrl.keys())
                assert not missing, (
                    f"Control '{ctrl.get('id', '?')}' in '{path.name}' is missing fields: {missing}"
                )

    @pytest.mark.asyncio
    async def test_upsert_called_for_each_yaml(self):
        """With 2 YAML files in a temp dir, _upsert_framework (and pool.acquire) called twice."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(tmpdir, "fw-alpha.yaml", _minimal_framework_yaml("fw-alpha"))
            _write_yaml(tmpdir, "fw-beta.yaml", _minimal_framework_yaml("fw-beta"))

            pool, conn = _make_pool()
            loader = FrameworkLoader(pool, tmpdir)
            results = await loader.load_all()

        assert len(results) == 2
        assert "fw-alpha" in results
        assert "fw-beta" in results
        # Each call to _upsert_framework acquires the pool once; at minimum 2 acquires occurred
        assert pool.acquire.call_count >= 2

    @pytest.mark.asyncio
    async def test_empty_frameworks_dir_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pool, _ = _make_pool()
            loader = FrameworkLoader(pool, tmpdir)
            result = await loader.load_all()

        assert result == {}

    @pytest.mark.asyncio
    async def test_invalid_yaml_does_not_crash(self, caplog):
        """One valid + one malformed YAML: valid one loads, error logged, no exception raised."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Valid framework
            _write_yaml(tmpdir, "valid-fw.yaml", _minimal_framework_yaml("valid-fw"))

            # Malformed YAML
            bad_path = Path(tmpdir) / "broken-fw.yaml"
            bad_path.write_text("slug: broken\ncontrols: [: this is not valid yaml", encoding="utf-8")

            pool, _ = _make_pool()
            loader = FrameworkLoader(pool, tmpdir)

            with caplog.at_level(logging.ERROR):
                result = await loader.load_all()

        assert "valid-fw" in result, "Valid framework must still be loaded"
        assert "broken-fw" not in result, "Broken framework must not appear in results"
        # An error should have been logged for the broken file
        assert any("broken-fw" in rec.message or "broken-fw.yaml" in rec.message
                   for rec in caplog.records), "Expected error log for broken-fw.yaml"
