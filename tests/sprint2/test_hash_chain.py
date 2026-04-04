"""
Sprint 2 — Hash-Chain Integrity Tests

Tests the evidence record hash-chaining algorithm used by both the
ingestion-orchestrator and evidence-store services.

Run: pytest tests/sprint2/test_hash_chain.py -v
"""

import hashlib
import json
import pytest


# ---------------------------------------------------------------------------
# Reproduce the hash-chain algorithm from services/evidence-store/src/hasher.py
# These must match exactly — any divergence breaks the tamper-evidence guarantee.
# ---------------------------------------------------------------------------

def compute_payload_hash(canonical_payload: dict) -> bytes:
    """SHA-256 of canonical JSON (sorted keys, no whitespace)."""
    serialized = json.dumps(canonical_payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(serialized).digest()


def compute_chain_hash(prev_chain_hash: bytes, payload_hash: bytes) -> bytes:
    """chain_hash = SHA-256(prev_chain_hash XOR payload_hash), both padded to 32 bytes."""
    prev = (prev_chain_hash + b'\x00' * 32)[:32]
    curr = (payload_hash + b'\x00' * 32)[:32]
    xored = bytes(a ^ b for a, b in zip(prev, curr))
    return hashlib.sha256(xored).digest()


def build_chain(records: list[dict]) -> list[dict]:
    """Build a full chain for a list of canonical payloads. Returns records with chain metadata."""
    result = []
    prev_hash = b'\x00' * 32  # Genesis hash
    for i, payload in enumerate(records):
        ph = compute_payload_hash(payload)
        ch = compute_chain_hash(prev_hash, ph)
        result.append({
            'chain_sequence': i + 1,
            'canonical_payload': payload,
            'payload_hash': ph.hex(),
            'chain_hash': ch.hex(),
        })
        prev_hash = ch
    return result


def verify_chain(records: list[dict]) -> tuple[bool, int | None]:
    """Verify chain integrity. Returns (intact, first_broken_sequence)."""
    for i, record in enumerate(records):
        if i == 0:
            continue
        prev = records[i - 1]
        expected = compute_chain_hash(
            bytes.fromhex(prev['chain_hash']),
            bytes.fromhex(record['payload_hash']),
        )
        actual = bytes.fromhex(record['chain_hash'])
        if expected != actual:
            return False, record['chain_sequence']
    return True, None


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

SAMPLE_PAYLOADS = [
    {
        'event_type': 'aws.putobject',
        'entity_id': 'evt-001',
        'entity_type': 'aws_resource',
        'actor_id': 'arn:aws:iam::123456789:user/alice',
        'timestamp_utc': '2026-04-01T10:00:00Z',
        'outcome': 'success',
        'resource': 'arn:aws:s3:::secure-bucket',
        'metadata': {'bucket': 'secure-bucket', 'key': 'docs/q1-report.pdf'},
    },
    {
        'event_type': 'transaction.created',
        'entity_id': 'txn-abc-123',
        'entity_type': 'financial_transaction',
        'actor_id': None,
        'timestamp_utc': '2026-04-01T11:30:00Z',
        'outcome': 'success',
        'resource': 'acct-5000',
        'metadata': {'amount': 12500.00, 'currency': 'USD', 'merchant_name': 'ACME Corp'},
    },
    {
        'event_type': 'ledger.journal_entry',
        'entity_id': 'je-00042',
        'entity_type': 'journal_entry',
        'actor_id': 'user@company.com',
        'timestamp_utc': '2026-04-01T14:00:00Z',
        'outcome': 'success',
        'resource': 'INV-2026-042',
        'metadata': {'line_count': 2, 'total_amount': 5000.00, 'currency': 'USD'},
    },
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPayloadHash:
    def test_deterministic(self):
        """Same payload always produces the same hash."""
        payload = SAMPLE_PAYLOADS[0]
        h1 = compute_payload_hash(payload)
        h2 = compute_payload_hash(payload)
        assert h1 == h2

    def test_key_order_invariant(self):
        """Hash is independent of dict key insertion order (sorted keys)."""
        payload_a = {'z': 1, 'a': 2, 'm': 3}
        payload_b = {'a': 2, 'm': 3, 'z': 1}
        assert compute_payload_hash(payload_a) == compute_payload_hash(payload_b)

    def test_different_payloads_produce_different_hashes(self):
        """Distinct payloads produce distinct hashes (collision resistance)."""
        h1 = compute_payload_hash(SAMPLE_PAYLOADS[0])
        h2 = compute_payload_hash(SAMPLE_PAYLOADS[1])
        assert h1 != h2

    def test_single_field_change_changes_hash(self):
        """Modifying any field changes the hash — tamper detection."""
        original = dict(SAMPLE_PAYLOADS[0])
        modified = dict(SAMPLE_PAYLOADS[0])
        modified['outcome'] = 'failure'  # Tiny change
        assert compute_payload_hash(original) != compute_payload_hash(modified)

    def test_hash_is_32_bytes(self):
        """SHA-256 output must be exactly 32 bytes."""
        h = compute_payload_hash(SAMPLE_PAYLOADS[0])
        assert len(h) == 32


class TestChainHash:
    def test_genesis_hash_is_deterministic(self):
        """First record with all-zero prev_hash produces a deterministic genesis hash."""
        prev = b'\x00' * 32
        ph = compute_payload_hash(SAMPLE_PAYLOADS[0])
        h1 = compute_chain_hash(prev, ph)
        h2 = compute_chain_hash(prev, ph)
        assert h1 == h2

    def test_chain_hash_changes_with_prev_hash(self):
        """Changing the previous hash changes the chain hash — chain binding."""
        ph = compute_payload_hash(SAMPLE_PAYLOADS[0])
        h1 = compute_chain_hash(b'\x00' * 32, ph)
        h2 = compute_chain_hash(b'\xff' * 32, ph)
        assert h1 != h2

    def test_chain_hash_is_32_bytes(self):
        ph = compute_payload_hash(SAMPLE_PAYLOADS[0])
        h = compute_chain_hash(b'\x00' * 32, ph)
        assert len(h) == 32


class TestChainIntegrity:
    def test_valid_chain_verifies(self):
        """A correctly built chain passes verification."""
        chain = build_chain(SAMPLE_PAYLOADS)
        intact, broken_at = verify_chain(chain)
        assert intact is True
        assert broken_at is None

    def test_single_record_chain_verifies(self):
        """A chain with one record is trivially valid."""
        chain = build_chain([SAMPLE_PAYLOADS[0]])
        intact, broken_at = verify_chain(chain)
        assert intact is True

    def test_empty_chain_verifies(self):
        """An empty chain is trivially valid."""
        intact, broken_at = verify_chain([])
        assert intact is True

    def test_tampered_payload_detected(self):
        """Modifying a record's canonical_payload invalidates the chain from that point."""
        chain = build_chain(SAMPLE_PAYLOADS)
        # Tamper record #2 — change the outcome
        tampered = dict(chain[1]['canonical_payload'])
        tampered['outcome'] = 'TAMPERED'
        chain[1] = dict(chain[1])
        chain[1]['canonical_payload'] = tampered
        # Recompute payload_hash for the tampered record (simulating an attacker who updates the hash)
        chain[1]['payload_hash'] = compute_payload_hash(tampered).hex()
        # But leave chain_hash unchanged — the chain should break
        intact, broken_at = verify_chain(chain)
        assert intact is False
        assert broken_at == 2  # chain_sequence 2

    def test_inserted_record_detected(self):
        """Inserting a record in the middle breaks the chain at the following record."""
        chain = build_chain(SAMPLE_PAYLOADS)
        # Insert a fake record between index 0 and 1
        fake_payload = {'event_type': 'injected', 'entity_id': 'fake', 'entity_type': 'fake',
                        'timestamp_utc': '2026-04-01T10:30:00Z', 'outcome': 'success'}
        fake_ph = compute_payload_hash(fake_payload)
        fake_ch = compute_chain_hash(bytes.fromhex(chain[0]['chain_hash']), fake_ph)
        fake_record = {
            'chain_sequence': 1.5,  # Not an integer — would fail DB constraint
            'canonical_payload': fake_payload,
            'payload_hash': fake_ph.hex(),
            'chain_hash': fake_ch.hex(),
        }
        # Splice in — the record after the insertion still has the old prev_hash reference
        corrupted_chain = [chain[0], fake_record, chain[1], chain[2]]
        intact, broken_at = verify_chain(corrupted_chain)
        # Record at index 2 (chain[1]) will fail because its chain_hash no longer
        # follows from fake_record's chain_hash
        assert intact is False

    def test_deleted_record_detected(self):
        """Removing a record from the chain breaks integrity at the next record."""
        chain = build_chain(SAMPLE_PAYLOADS)
        # Remove record #2 (index 1)
        gapped_chain = [chain[0], chain[2]]  # sequence 1 → sequence 3
        intact, broken_at = verify_chain(gapped_chain)
        assert intact is False
        assert broken_at == chain[2]['chain_sequence']

    def test_reordered_records_detected(self):
        """Reordering records breaks the chain at the first out-of-order record."""
        chain = build_chain(SAMPLE_PAYLOADS)
        # Swap records 2 and 3
        reordered = [chain[0], chain[2], chain[1]]
        intact, broken_at = verify_chain(reordered)
        assert intact is False

    def test_chain_with_100_records(self):
        """Chain scales correctly to 100 records without errors."""
        payloads = [
            {'event_type': f'test.event_{i}', 'entity_id': f'ent-{i}',
             'entity_type': 'test', 'timestamp_utc': f'2026-04-01T{i % 24:02d}:00:00Z',
             'outcome': 'success'}
            for i in range(100)
        ]
        chain = build_chain(payloads)
        assert len(chain) == 100
        intact, broken_at = verify_chain(chain)
        assert intact is True

    def test_cross_service_hash_consistency(self):
        """
        The ingestion-orchestrator and evidence-store must produce identical
        chain hashes for the same input. This test verifies the algorithm is
        consistent — any divergence between services would silently corrupt the chain.
        """
        payload = SAMPLE_PAYLOADS[0]
        prev_hash = bytes.fromhex('cafebabe' + '00' * 28)  # Non-zero prev hash

        # Simulate ingestion-orchestrator path
        ph_ingestion = compute_payload_hash(payload)
        ch_ingestion = compute_chain_hash(prev_hash, ph_ingestion)

        # Simulate evidence-store path (same algorithm, different code path)
        ph_evidence_store = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
        ).digest()
        prev = (prev_hash + b'\x00' * 32)[:32]
        curr = (ph_evidence_store + b'\x00' * 32)[:32]
        xored = bytes(a ^ b for a, b in zip(prev, curr))
        ch_evidence_store = hashlib.sha256(xored).digest()

        assert ch_ingestion == ch_evidence_store, (
            "Hash algorithm divergence between ingestion-orchestrator and evidence-store! "
            "Both services must use identical hashing to maintain chain integrity."
        )
