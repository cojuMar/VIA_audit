from __future__ import annotations

import asyncpg
import structlog

from .config import settings
from .hasher import ChainState
from .models import EvidenceRecordCreate

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Pool lifecycle
# ---------------------------------------------------------------------------


async def create_pool() -> asyncpg.Pool:
    pool = await asyncpg.create_pool(
        settings.database_url,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )
    logger.info("db_pool_created")
    return pool


async def close_pool(pool: asyncpg.Pool) -> None:
    await pool.close()
    logger.info("db_pool_closed")


# ---------------------------------------------------------------------------
# RLS helper
# ---------------------------------------------------------------------------

async def _set_tenant_context(conn: asyncpg.Connection, tenant_id: str) -> None:
    """Sets the app.tenant_id session variable consumed by PostgreSQL RLS policies."""
    await conn.execute("SELECT set_config('app.tenant_id', $1, false)", tenant_id)


# ---------------------------------------------------------------------------
# Chain state
# ---------------------------------------------------------------------------

GENESIS_HASH = b"\x00" * 32  # Hash used as prev_chain_hash for the very first record


async def get_chain_state(pool: asyncpg.Pool, tenant_id: str) -> ChainState:
    """
    Returns the ChainState (last hash + next sequence number) for the given tenant.
    If no records exist yet, returns the genesis state (zeros, sequence=1).
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _set_tenant_context(conn, tenant_id)
            row = await conn.fetchrow(
                """
                SELECT chain_hash, chain_sequence
                FROM evidence_records
                WHERE tenant_id = $1
                ORDER BY chain_sequence DESC
                LIMIT 1
                """,
                tenant_id,
            )

    if row is None:
        return ChainState(last_hash=GENESIS_HASH, next_seq=1)

    chain_hash_val = row["chain_hash"]
    if isinstance(chain_hash_val, str):
        last_hash = bytes.fromhex(chain_hash_val)
    else:
        last_hash = bytes(chain_hash_val)

    return ChainState(last_hash=last_hash, next_seq=row["chain_sequence"] + 1)


# ---------------------------------------------------------------------------
# Insert
# ---------------------------------------------------------------------------

async def insert_evidence_record(
    pool: asyncpg.Pool,
    record: EvidenceRecordCreate,
    chain_hash: bytes,
    chain_sequence: int,
    tenant_id: str,
) -> str:
    """
    Inserts the evidence record inside a tenant-scoped transaction (RLS-compatible).

    Uses ON CONFLICT DO NOTHING to be idempotent on the
    UNIQUE(tenant_id, chain_sequence) constraint.

    Returns the evidence_id as a string.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _set_tenant_context(conn, tenant_id)
            await conn.execute(
                """
                INSERT INTO evidence_records (
                    evidence_id,
                    tenant_id,
                    source_system,
                    collected_at_utc,
                    payload_hash,
                    canonical_payload,
                    collector_version,
                    chain_sequence,
                    chain_hash,
                    freshness_status
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (tenant_id, chain_sequence) DO NOTHING
                """,
                str(record.evidence_id),
                str(record.tenant_id),
                record.source_system,
                record.collected_at_utc,
                record.payload_hash,
                # asyncpg accepts dicts for jsonb columns
                record.canonical_payload,
                record.collector_version,
                chain_sequence,
                chain_hash.hex(),
                "fresh",
            )

    logger.info(
        "evidence_inserted",
        evidence_id=str(record.evidence_id),
        tenant_id=tenant_id,
        chain_sequence=chain_sequence,
    )
    return str(record.evidence_id)


# ---------------------------------------------------------------------------
# Chain verification
# ---------------------------------------------------------------------------

async def get_records_for_chain_verify(
    pool: asyncpg.Pool, tenant_id: str, limit: int = 100
) -> list[dict]:
    """
    Returns the last *limit* records for a tenant ordered by chain_sequence ASC.
    Each dict contains at minimum: chain_sequence, chain_hash, payload_hash.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _set_tenant_context(conn, tenant_id)
            rows = await conn.fetch(
                """
                SELECT evidence_id, chain_sequence, chain_hash, payload_hash
                FROM evidence_records
                WHERE tenant_id = $1
                ORDER BY chain_sequence DESC
                LIMIT $2
                """,
                tenant_id,
                limit,
            )

    # Reverse so that we have ASC order for verification
    return [dict(r) for r in reversed(rows)]


# ---------------------------------------------------------------------------
# WORM promotion helpers
# ---------------------------------------------------------------------------

async def get_pending_worm_records(
    pool: asyncpg.Pool, tenant_id: str, batch_size: int
) -> list[dict]:
    """
    Returns records that have not yet been promoted to WORM storage.
    Identifies un-promoted records by checking for the absence of 'worm_uri'
    in canonical_payload metadata.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _set_tenant_context(conn, tenant_id)
            rows = await conn.fetch(
                """
                SELECT
                    evidence_id,
                    tenant_id,
                    source_system,
                    collected_at_utc,
                    payload_hash,
                    canonical_payload,
                    collector_version,
                    chain_sequence,
                    chain_hash,
                    freshness_status,
                    created_at
                FROM evidence_records
                WHERE tenant_id = $1
                  AND (
                      canonical_payload->>'worm_promoted' IS NULL
                      OR canonical_payload->>'worm_promoted' = 'false'
                  )
                ORDER BY created_at ASC
                LIMIT $2
                """,
                tenant_id,
                batch_size,
            )

    return [dict(r) for r in rows]


async def update_worm_status(
    pool: asyncpg.Pool,
    evidence_id: str,
    tenant_id: str,
    worm_uri: str,
) -> None:
    """
    Marks a record as WORM-promoted by embedding the worm_uri into
    the canonical_payload JSON column.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _set_tenant_context(conn, tenant_id)
            await conn.execute(
                """
                UPDATE evidence_records
                SET canonical_payload = canonical_payload
                    || jsonb_build_object(
                        'worm_promoted', true,
                        'worm_uri', $3::text
                    )
                WHERE evidence_id = $1
                  AND tenant_id = $2
                """,
                evidence_id,
                tenant_id,
                worm_uri,
            )

    logger.info(
        "worm_status_updated",
        evidence_id=evidence_id,
        tenant_id=tenant_id,
        worm_uri=worm_uri,
    )


# ---------------------------------------------------------------------------
# Admin helpers (no tenant RLS — used by background workers only)
# ---------------------------------------------------------------------------

async def get_all_tenant_ids_with_pending_worm(pool: asyncpg.Pool) -> list[str]:
    """
    Returns distinct tenant_ids that have at least one un-promoted record.
    Runs without SET LOCAL app.tenant_id, so the caller must be a superuser
    or use a role that bypasses RLS (e.g., the service role).
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT tenant_id::text
            FROM evidence_records
            WHERE canonical_payload->>'worm_promoted' IS NULL
               OR canonical_payload->>'worm_promoted' = 'false'
            """
        )
    return [r["tenant_id"] for r in rows]


# ---------------------------------------------------------------------------
# Query helpers for the HTTP API
# ---------------------------------------------------------------------------

async def get_evidence_by_id(
    pool: asyncpg.Pool, evidence_id: str, tenant_id: str
) -> dict | None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _set_tenant_context(conn, tenant_id)
            row = await conn.fetchrow(
                """
                SELECT
                    evidence_id,
                    tenant_id,
                    source_system,
                    collected_at_utc,
                    chain_sequence,
                    chain_hash,
                    freshness_status,
                    zk_proof_id,
                    created_at
                FROM evidence_records
                WHERE evidence_id = $1
                  AND tenant_id = $2
                """,
                evidence_id,
                tenant_id,
            )
    return dict(row) if row else None


async def list_evidence_records(
    pool: asyncpg.Pool,
    tenant_id: str,
    limit: int = 50,
    offset: int = 0,
    source_system: str | None = None,
    collected_after: str | None = None,
    collected_before: str | None = None,
) -> list[dict]:
    filters = ["tenant_id = $1"]
    params: list = [tenant_id]
    idx = 2

    if source_system:
        filters.append(f"source_system = ${idx}")
        params.append(source_system)
        idx += 1
    if collected_after:
        filters.append(f"collected_at_utc >= ${idx}")
        params.append(collected_after)
        idx += 1
    if collected_before:
        filters.append(f"collected_at_utc <= ${idx}")
        params.append(collected_before)
        idx += 1

    where_clause = " AND ".join(filters)
    params.extend([limit, offset])

    async with pool.acquire() as conn:
        async with conn.transaction():
            await _set_tenant_context(conn, tenant_id)
            rows = await conn.fetch(
                f"""
                SELECT
                    evidence_id,
                    tenant_id,
                    source_system,
                    collected_at_utc,
                    chain_sequence,
                    chain_hash,
                    freshness_status,
                    zk_proof_id,
                    created_at
                FROM evidence_records
                WHERE {where_clause}
                ORDER BY chain_sequence ASC
                LIMIT ${idx} OFFSET ${idx + 1}
                """,
                *params,
            )
    return [dict(r) for r in rows]
