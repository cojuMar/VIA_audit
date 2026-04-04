import asyncpg


class ConnectorRegistry:
    async def list_connectors(self, pool: asyncpg.Pool) -> list[dict]:
        """List all active connectors (no tenant context needed)."""
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    connector_key,
                    display_name,
                    category,
                    auth_type,
                    supported_data_types,
                    description,
                    logo_url,
                    is_active,
                    created_at
                FROM connector_definitions
                WHERE is_active = true
                ORDER BY category, display_name
                """
            )
        return [dict(r) for r in rows]

    async def get_connector(self, pool: asyncpg.Pool, connector_key: str) -> dict | None:
        """Fetch a single connector by key (no tenant context)."""
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id,
                    connector_key,
                    display_name,
                    category,
                    auth_type,
                    supported_data_types,
                    description,
                    logo_url,
                    config_schema,
                    is_active,
                    created_at
                FROM connector_definitions
                WHERE connector_key = $1
                """,
                connector_key,
            )
        return dict(row) if row else None

    async def get_field_mapping_templates(
        self,
        pool: asyncpg.Pool,
        connector_key: str,
        data_type: str,
    ) -> list[dict]:
        """Return field mapping templates for a connector + data_type."""
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    fmt.id,
                    fmt.data_type,
                    fmt.source_field,
                    fmt.target_field,
                    fmt.transform_fn,
                    fmt.is_required,
                    fmt.description
                FROM field_mapping_templates fmt
                JOIN connector_definitions cd ON cd.id = fmt.connector_id
                WHERE cd.connector_key = $1
                  AND fmt.data_type = $2
                ORDER BY fmt.is_required DESC, fmt.source_field
                """,
                connector_key,
                data_type,
            )
        return [dict(r) for r in rows]
