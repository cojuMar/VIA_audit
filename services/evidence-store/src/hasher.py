import hashlib
import json
from dataclasses import dataclass


@dataclass
class ChainState:
    last_hash: bytes  # chain_hash of the most recent record
    next_seq: int     # next chain_sequence value


def compute_payload_hash(canonical_payload: dict) -> bytes:
    """
    SHA-256 of canonical JSON serialization (sorted keys, no whitespace).
    Must be identical across all services to produce consistent hashes.
    """
    serialized = json.dumps(
        canonical_payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(serialized).digest()


def compute_chain_hash(prev_chain_hash: bytes, payload_hash: bytes) -> bytes:
    """
    chain_hash = SHA-256(prev_chain_hash XOR payload_hash)
    prev_chain_hash and payload_hash are padded/truncated to 32 bytes.
    """
    prev = (prev_chain_hash + b"\x00" * 32)[:32]
    curr = (payload_hash + b"\x00" * 32)[:32]
    xored = bytes(a ^ b for a, b in zip(prev, curr))
    return hashlib.sha256(xored).digest()


def verify_chain_segment(records: list[dict]) -> tuple[bool, int | None]:
    """
    Verifies that a list of records (sorted by chain_sequence ASC) form a valid chain.
    Returns (intact: bool, first_broken_sequence: int | None)
    """
    for i, record in enumerate(records):
        if i == 0:
            continue
        prev = records[i - 1]
        expected = compute_chain_hash(
            bytes.fromhex(prev["chain_hash"])
            if isinstance(prev["chain_hash"], str)
            else prev["chain_hash"],
            bytes.fromhex(record["payload_hash"])
            if isinstance(record["payload_hash"], str)
            else record["payload_hash"],
        )
        actual = (
            bytes.fromhex(record["chain_hash"])
            if isinstance(record["chain_hash"], str)
            else record["chain_hash"]
        )
        if expected != actual:
            return False, record["chain_sequence"]
    return True, None
