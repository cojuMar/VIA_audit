"""
Loads framework YAML definitions from disk and upserts into the DB.
Called at service startup and via POST /admin/reload-frameworks.

YAML structure expected:
  slug, name, version, category, issuing_body, description, metadata{}, domains[], controls[]
  Each control: id, domain, title, description, guidance?, evidence_types[], testing_frequency, is_key_control
"""
import os
import yaml
import logging
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class FrameworkLoader:
    def __init__(self, db_pool, frameworks_dir: str):
        self._pool = db_pool
        self._dir = Path(frameworks_dir)

    async def load_all(self) -> Dict[str, int]:
        """Load all .yaml files from frameworks_dir. Returns {slug: controls_loaded}."""
        results = {}
        yaml_files = sorted(self._dir.glob("*.yaml"))
        if not yaml_files:
            logger.warning(f"No YAML files found in {self._dir}")
            return results

        for path in yaml_files:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                count = await self._upsert_framework(data)
                results[data['slug']] = count
                logger.info(f"Loaded {count} controls for framework '{data['slug']}'")
            except Exception as e:
                logger.error(f"Failed to load {path.name}: {e}")

        return results

    async def _upsert_framework(self, data: Dict[str, Any]) -> int:
        """Upsert framework + controls. Returns count of controls upserted."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Upsert framework
                framework_id = await conn.fetchval("""
                    INSERT INTO compliance_frameworks
                        (slug, name, version, category, description, issuing_body, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                    ON CONFLICT (slug) DO UPDATE SET
                        name = EXCLUDED.name,
                        version = EXCLUDED.version,
                        category = EXCLUDED.category,
                        description = EXCLUDED.description,
                        issuing_body = EXCLUDED.issuing_body,
                        metadata = EXCLUDED.metadata
                    RETURNING id
                """,
                    data['slug'], data['name'], data['version'],
                    data['category'], data['description'], data['issuing_body'],
                    __import__('json').dumps(data.get('metadata', {}))
                )

                # Upsert controls
                controls = data.get('controls', [])
                for ctrl in controls:
                    await conn.execute("""
                        INSERT INTO framework_controls
                            (framework_id, control_id, domain, title, description,
                             guidance, evidence_types, testing_frequency, is_key_control)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        ON CONFLICT (framework_id, control_id) DO UPDATE SET
                            domain = EXCLUDED.domain,
                            title = EXCLUDED.title,
                            description = EXCLUDED.description,
                            guidance = EXCLUDED.guidance,
                            evidence_types = EXCLUDED.evidence_types,
                            testing_frequency = EXCLUDED.testing_frequency,
                            is_key_control = EXCLUDED.is_key_control
                    """,
                        framework_id,
                        ctrl['id'], ctrl['domain'], ctrl['title'], ctrl['description'],
                        ctrl.get('guidance'), ctrl.get('evidence_types', []),
                        ctrl.get('testing_frequency', 'annual'),
                        ctrl.get('is_key_control', False)
                    )

                return len(controls)
