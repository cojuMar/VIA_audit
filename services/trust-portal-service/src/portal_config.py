import logging
import re
from uuid import uuid4

import asyncpg

from .db import tenant_conn

logger = logging.getLogger(__name__)

_VALID_SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$|^[a-z0-9]$')


class PortalConfigManager:
    """CRUD for trust_portal_configs table."""

    @staticmethod
    def validate_slug(slug: str) -> None:
        """Raise ValueError if slug contains uppercase, spaces, or invalid characters.

        Valid slugs are lowercase alphanumeric with hyphens only (no leading/trailing hyphen).
        """
        if slug != slug.lower():
            raise ValueError(
                f"Slug must be lowercase — '{slug}' contains uppercase characters"
            )
        if ' ' in slug:
            raise ValueError(f"Slug must not contain spaces — got '{slug}'")
        if not _VALID_SLUG_RE.match(slug):
            raise ValueError(
                f"Slug '{slug}' is invalid — only lowercase letters, digits, "
                "and hyphens are allowed (no leading/trailing hyphens)"
            )

    async def get_by_slug(self, pool: asyncpg.Pool, slug: str) -> dict | None:
        """Public lookup — no RLS needed; slug is globally unique."""
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, tenant_id, slug, company_name, tagline, logo_url,
                       primary_color, portal_enabled, require_nda, nda_version,
                       show_compliance_scores, chatbot_enabled,
                       chatbot_welcome_message, allowed_frameworks
                FROM trust_portal_configs
                WHERE slug = $1 AND portal_enabled = true
                """,
                slug,
            )
        if row is None:
            return None
        return dict(row)

    async def get_by_tenant(self, pool: asyncpg.Pool, tenant_id: str) -> dict | None:
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT id, tenant_id, slug, company_name, tagline, logo_url,
                       primary_color, portal_enabled, require_nda, nda_version,
                       show_compliance_scores, chatbot_enabled,
                       chatbot_welcome_message, allowed_frameworks
                FROM trust_portal_configs
                WHERE tenant_id = $1
                """,
                tenant_id,
            )
        if row is None:
            return None
        return dict(row)

    async def upsert(
        self, pool: asyncpg.Pool, tenant_id: str, data: dict
    ) -> dict:
        """INSERT … ON CONFLICT (tenant_id) DO UPDATE.

        ``data`` should contain the fields to set; id is generated if not provided.
        """
        record_id = str(data.get("id", uuid4()))
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO trust_portal_configs (
                    id, tenant_id, slug, company_name, tagline, logo_url,
                    primary_color, portal_enabled, require_nda, nda_version,
                    show_compliance_scores, chatbot_enabled,
                    chatbot_welcome_message, allowed_frameworks
                ) VALUES (
                    $1, $2, $3, $4, $5, $6,
                    $7, $8, $9, $10,
                    $11, $12,
                    $13, $14
                )
                ON CONFLICT (tenant_id) DO UPDATE SET
                    slug                  = EXCLUDED.slug,
                    company_name          = EXCLUDED.company_name,
                    tagline               = EXCLUDED.tagline,
                    logo_url              = EXCLUDED.logo_url,
                    primary_color         = EXCLUDED.primary_color,
                    portal_enabled        = EXCLUDED.portal_enabled,
                    require_nda           = EXCLUDED.require_nda,
                    nda_version           = EXCLUDED.nda_version,
                    show_compliance_scores = EXCLUDED.show_compliance_scores,
                    chatbot_enabled       = EXCLUDED.chatbot_enabled,
                    chatbot_welcome_message = EXCLUDED.chatbot_welcome_message,
                    allowed_frameworks    = EXCLUDED.allowed_frameworks,
                    updated_at            = NOW()
                RETURNING *
                """,
                record_id,
                tenant_id,
                data.get("slug"),
                data.get("company_name"),
                data.get("tagline"),
                data.get("logo_url"),
                data.get("primary_color", "#0066CC"),
                data.get("portal_enabled", True),
                data.get("require_nda", False),
                data.get("nda_version", "1.0"),
                data.get("show_compliance_scores", True),
                data.get("chatbot_enabled", False),
                data.get("chatbot_welcome_message"),
                data.get("allowed_frameworks", []),
            )
        return dict(row)
