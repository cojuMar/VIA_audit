"""
Sprint 7 — Post-Quantum Cryptography Tests

Tests CRYSTALS-Kyber KEM and CRYSTALS-Dilithium signature implementations.
If liboqs is not available, tests are skipped gracefully.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/pq-crypto-service'))

import pytest
import hashlib

# Check if liboqs is available
try:
    import oqs  # noqa: F401 — availability probe; ruff doesn't see the try/except idiom
    OQS_AVAILABLE = True
except ImportError:
    OQS_AVAILABLE = False

pytestmark = pytest.mark.skipif(not OQS_AVAILABLE, reason="liboqs not available")


# ---------------------------------------------------------------------------
# Helpers — imported lazily so the module loads even without liboqs
# ---------------------------------------------------------------------------

def get_kyber():
    from src.kyber_kem import KyberKEM
    return KyberKEM()


def get_dilithium():
    from src.dilithium_signer import DilithiumSigner
    return DilithiumSigner()


# ---------------------------------------------------------------------------
# CRYSTALS-Kyber KEM
# ---------------------------------------------------------------------------

class TestKyberKEM:

    def test_keypair_generation_produces_bytes(self):
        kem = get_kyber()
        public_key, secret_key = kem.generate_keypair()
        assert isinstance(public_key, bytes) and len(public_key) > 0
        assert isinstance(secret_key, bytes) and len(secret_key) > 0

    def test_public_key_fingerprint_is_sha256(self):
        kem = get_kyber()
        public_key, _ = kem.generate_keypair()
        fingerprint = kem.fingerprint(public_key)
        expected = hashlib.sha256(public_key).digest()
        assert fingerprint == expected

    def test_encapsulate_produces_ciphertext_and_secret(self):
        kem = get_kyber()
        public_key, _ = kem.generate_keypair()
        ciphertext, shared_secret = kem.encapsulate(public_key)
        assert isinstance(ciphertext, bytes) and len(ciphertext) > 0
        assert isinstance(shared_secret, bytes) and len(shared_secret) > 0

    def test_decapsulate_roundtrip(self):
        kem = get_kyber()
        public_key, secret_key = kem.generate_keypair()
        ciphertext, shared_secret_enc = kem.encapsulate(public_key)
        shared_secret_dec = kem.decapsulate(ciphertext, secret_key)
        assert shared_secret_enc == shared_secret_dec

    def test_different_keypairs_produce_different_ciphertexts(self):
        kem = get_kyber()
        public_key, _ = kem.generate_keypair()
        ciphertext_1, _ = kem.encapsulate(public_key)
        ciphertext_2, _ = kem.encapsulate(public_key)
        # Kyber encapsulation is randomised — two calls must produce different ciphertexts
        assert ciphertext_1 != ciphertext_2

    def test_wrong_secret_key_fails_decapsulation(self):
        kem = get_kyber()
        public_key_a, secret_key_a = kem.generate_keypair()
        _public_key_b, secret_key_b = kem.generate_keypair()

        ciphertext, shared_secret_correct = kem.encapsulate(public_key_a)
        # IND-CCA2: decapsulating with a wrong key produces garbage, not an exception
        shared_secret_wrong = kem.decapsulate(ciphertext, secret_key_b)
        assert shared_secret_correct != shared_secret_wrong

    def test_algorithm_constant_is_kyber768(self):
        from src.kyber_kem import KyberKEM
        assert KyberKEM.ALGORITHM == "Kyber768"


# ---------------------------------------------------------------------------
# CRYSTALS-Dilithium Signer
# ---------------------------------------------------------------------------

class TestDilithiumSigner:

    def test_keypair_generation_produces_bytes(self):
        signer = get_dilithium()
        public_key, secret_key = signer.generate_keypair()
        assert isinstance(public_key, bytes) and len(public_key) > 0
        assert isinstance(secret_key, bytes) and len(secret_key) > 0

    def test_sign_produces_non_empty_bytes(self):
        signer = get_dilithium()
        public_key, secret_key = signer.generate_keypair()
        signature = signer.sign(b"test message", secret_key)
        assert isinstance(signature, bytes) and len(signature) > 0

    def test_verify_valid_signature(self):
        signer = get_dilithium()
        public_key, secret_key = signer.generate_keypair()
        message = b"audit narrative payload for Q1 2026"
        signature = signer.sign(message, secret_key)
        assert signer.verify(message, signature, public_key) is True

    def test_verify_tampered_message(self):
        signer = get_dilithium()
        public_key, secret_key = signer.generate_keypair()
        message = b"original audit payload"
        signature = signer.sign(message, secret_key)
        tampered = bytearray(message)
        tampered[0] ^= 0xFF
        assert signer.verify(bytes(tampered), signature, public_key) is False

    def test_verify_tampered_signature(self):
        signer = get_dilithium()
        public_key, secret_key = signer.generate_keypair()
        message = b"original audit payload"
        signature = bytearray(signer.sign(message, secret_key))
        signature[0] ^= 0xFF
        assert signer.verify(message, bytes(signature), public_key) is False

    def test_verify_wrong_public_key(self):
        signer = get_dilithium()
        public_key_a, secret_key_a = signer.generate_keypair()
        public_key_b, _secret_key_b = signer.generate_keypair()
        message = b"message signed by keypair A"
        signature = signer.sign(message, secret_key_a)
        assert signer.verify(message, signature, public_key_b) is False

    def test_verify_never_raises(self):
        signer = get_dilithium()
        public_key, _ = signer.generate_keypair()
        # Passing garbage bytes should return False without raising any exception
        result = signer.verify(b"garbage message", b"\x00" * 32, public_key)
        assert result is False

    def test_algorithm_constant_is_dilithium3(self):
        from src.dilithium_signer import DilithiumSigner
        assert DilithiumSigner.ALGORITHM == "Dilithium3"

    def test_different_messages_produce_different_signatures(self):
        signer = get_dilithium()
        _public_key, secret_key = signer.generate_keypair()
        sig_a = signer.sign(b"message alpha", secret_key)
        sig_b = signer.sign(b"message beta", secret_key)
        assert sig_a != sig_b
