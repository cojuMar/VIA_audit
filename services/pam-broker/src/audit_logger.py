from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

import asyncpg
import structlog

from .models import PAMAuditEntry

logger = structlog.get_logger(__name__)


def _xor_bytes(a: bytes, b: bytes) -> bytes:
    """XOR two byte strings of potentially different lengths (zero-pads shorter)."""
    len_max = max(len(a), len(b))
    a_padded = a.ljust(len_max, b"\x00")
    b_padded = b.ljust(len_max, b"\x00")
    return bytes(x ^ y for x, y in zip(a_padded, b_padded))


def _canonical_json(entry: PAMAuditEntry) -> bytes:
    """Serialize entry as canonical (sorted-keys) JSON bytes."""
    return json.dumps(entry.model_dump(mode="json"), sort_keys=True, default=str).encode()


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


class AuditLogger:
    def __init__(self, db_pool: asyncpg.Pool) -> None:
        self._pool = db_pool

    async def get_previous_chain_hash(self) -> Optional[bytes]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT chain_hash
                FROM pam_audit_log
                ORDER BY chain_sequence DESC
                LIMIT 1
                """
            )
        if row is None:
            return None
        value = row["chain_hash"]
        if isinstance(value, str):
            return bytes.fromhex(value)
        return bytes(value)

    async def log(self, entry: PAMAuditEntry) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # 1. Get and atomically increment chain sequence
                seq_row = await conn.fetchrow(
                    """
                    UPDATE chain_sequence_counters_pam
                    SET sequence_value = sequence_value + 1,
                        updated_at     = NOW()
                    WHERE counter_name = 'pam_audit_log'
                    RETURNING sequence_value
                    """
                )
                if seq_row is None:
                    # Bootstrap: insert initial counter if missing
                    seq_row = await conn.fetchrow(
                        """
                        INSERT INTO chain_sequence_counters_pam (counter_name, sequence_value, updated_at)
                        VALUES ('pam_audit_log', 1, NOW())
                        ON CONFLICT (counter_name) DO UPDATE
                            SET sequence_value = chain_sequence_counters_pam.sequence_value + 1,
                                updated_at     = NOW()
                        RETURNING sequence_value
                        """
                    )

                chain_sequence: int = seq_row["sequence_value"]

                # 2. Fetch previous chain hash (within same transaction for consistency)
                prev_row = await conn.fetchrow(
                    """
                    SELECT chain_hash
                    FROM pam_audit_log
                    ORDER BY chain_sequence DESC
                    LIMIT 1
                    """
                )
                if prev_row is None:
                    prev_hash = bytes(32)  # genesis: 32 zero bytes
                else:
                    raw = prev_row["chain_hash"]
                    prev_hash = bytes.fromhex(raw) if isinstance(raw, str) else bytes(raw)

                # 3. Compute chain hash: SHA-256(prev XOR SHA-256(entry_json))
                entry_hash = _sha256(_canonical_json(entry))
                chain_hash = _sha256(_xor_bytes(prev_hash, entry_hash))
                chain_hash_hex = chain_hash.hex()

                # 4. Redact query_text before persisting
                safe_query_text = "[REDACTED]" if entry.query_text else None

                # 5. Insert immutable audit row
                await conn.execute(
                    """
                    INSERT INTO pam_audit_log (
                        request_id, actor_user_id, actor_role, action,
                        resource, query_text, duration_ms, status_code,
                        ip_address, chain_sequence, chain_hash, recorded_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    """,
                    entry.request_id,
                    entry.actor_user_id,
                    entry.actor_role,
                    entry.action,
                    entry.resource,
                    safe_query_text,
                    entry.duration_ms,
                    entry.status_code,
                    entry.ip_address,
                    chain_sequence,
                    chain_hash_hex,
                    datetime.now(timezone.utc),
                )

        logger.info(
            "audit_log_written",
            request_id=entry.request_id,
            actor=entry.actor_user_id,
            action=entry.action,
            chain_sequence=chain_sequence,
        )

    async def verify_chain_integrity(self, limit: int = 100) -> dict:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT request_id, actor_user_id, actor_role, action,
                       resource, duration_ms, status_code, ip_address,
                       chain_sequence, chain_hash
                FROM pam_audit_log
                ORDER BY chain_sequence DESC
                LIMIT $1
                """,
                limit,
            )

        if not rows:
            return {"intact": True, "first_broken_sequence": None}

        # Reverse so we process oldest first
        rows = list(reversed(rows))

        first_broken: Optional[int] = None
        prev_hash = bytes(32)  # genesis sentinel

        for row in rows:
            # Reconstruct the entry (query_text was redacted; that's fine—chain is over stored values)
            entry = PAMAuditEntry(
                request_id=row["request_id"],
                actor_user_id=row["actor_user_id"],
                actor_role=row["actor_role"],
                action=row["action"],
                resource=row["resource"],
                query_text=None,  # stored as [REDACTED]; skip for reconstruction
                duration_ms=row["duration_ms"],
                status_code=row["status_code"],
                ip_address=row["ip_address"],
            )

            stored_hash_raw = row["chain_hash"]
            stored_hash = (
                bytes.fromhex(stored_hash_raw)
                if isinstance(stored_hash_raw, str)
                else bytes(stored_hash_raw)
            )

            entry_hash = _sha256(_canonical_json(entry))
            expected_hash = _sha256(_xor_bytes(prev_hash, entry_hash))

            if expected_hash != stored_hash:
                if first_broken is None:
                    first_broken = row["chain_sequence"]

            prev_hash = stored_hash

        return {
            "intact": first_broken is None,
            "first_broken_sequence": first_broken,
        }
