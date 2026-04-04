"""
Hash-chain computation for the ingestion layer.

Each canonical evidence record is linked to the previous one via a
XOR-then-SHA256 chain.  This creates a tamper-evident sequence: altering
any record breaks all subsequent chain hashes.

Chain integrity is verified by the evidence-store service; this module
is responsible only for computing the links at ingestion time.
"""

import hashlib
import json
from dataclasses import dataclass


@dataclass
class ChainLink:
    payload_hash: bytes  # SHA-256 of the raw canonical_payload JSON
    prev_chain_hash: bytes  # Previous record's chain_hash (all zeros for first record)
    chain_hash: bytes  # SHA-256(prev_chain_hash XOR payload_hash)
    chain_sequence: int


def compute_payload_hash(canonical_payload: dict) -> bytes:
    """
    Returns the SHA-256 hex digest (as ASCII bytes) of the canonically
    serialized canonical_payload JSON (sorted keys, no whitespace).
    """
    serialized = json.dumps(
        canonical_payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest().encode("ascii")


def compute_chain_hash(prev_chain_hash: bytes, payload_hash: bytes) -> bytes:
    """
    chain_hash = SHA-256(prev_chain_hash XOR payload_hash)

    Both inputs are truncated or zero-padded to exactly 32 bytes before XOR.
    XOR creates an irreversible cryptographic binding between the previous
    chain state and the current payload.
    """
    prev = prev_chain_hash.ljust(32, b"\x00")[:32]
    curr = payload_hash.ljust(32, b"\x00")[:32]
    xored = bytes(a ^ b for a, b in zip(prev, curr))
    return hashlib.sha256(xored).digest()


def build_chain_link(
    canonical_payload: dict,
    prev_chain_hash: bytes,
    chain_sequence: int,
) -> ChainLink:
    """
    Convenience wrapper that computes both hashes and returns a ChainLink.

    Parameters
    ----------
    canonical_payload:
        The dict stored in CanonicalEvidenceRecord.canonical_payload.
    prev_chain_hash:
        The chain_hash from the immediately preceding record for this
        (tenant_id, source_system) partition.  Pass 32 zero bytes for the
        very first record.
    chain_sequence:
        Monotonically increasing integer for ordering within the chain.
    """
    payload_hash = compute_payload_hash(canonical_payload)
    chain_hash = compute_chain_hash(prev_chain_hash, payload_hash)
    return ChainLink(
        payload_hash=payload_hash,
        prev_chain_hash=prev_chain_hash,
        chain_hash=chain_hash,
        chain_sequence=chain_sequence,
    )
