"""
CRYSTALS-Kyber-768 Key Encapsulation Mechanism (KEM)

Uses liboqs-python (Open Quantum Safe).
Kyber768 is NIST PQC Level 3 (equivalent to AES-192 security).

Key operations:
- generate_keypair() → (public_key: bytes, secret_key: bytes)
- encapsulate(public_key) → (ciphertext: bytes, shared_secret: bytes)
- decapsulate(ciphertext, secret_key) → shared_secret: bytes
"""

import hashlib
from dataclasses import dataclass, field

try:
    import oqs  # liboqs-python
    _OQS_AVAILABLE = True
except ImportError:
    _OQS_AVAILABLE = False
    oqs = None  # type: ignore[assignment]

ALGORITHM = "Kyber768"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class KyberKeypair:
    public_key: bytes
    secret_key: bytes
    algorithm: str = ALGORITHM
    fingerprint: bytes = field(init=False)  # SHA-256 of public_key

    def __post_init__(self):
        self.fingerprint = hashlib.sha256(self.public_key).digest()


@dataclass
class KyberEncapsulationResult:
    ciphertext: bytes
    shared_secret: bytes


# ---------------------------------------------------------------------------
# KEM
# ---------------------------------------------------------------------------

class KyberKEM:
    """Wrapper around liboqs Kyber768 KEM operations.

    All methods raise ValueError if liboqs is not available or if the
    underlying OQS call fails, so callers can surface a clean error without
    crashing the service.
    """

    def generate_keypair(self) -> KyberKeypair:
        """Generate a fresh Kyber768 keypair."""
        if not _OQS_AVAILABLE:
            raise ValueError("liboqs not available: oqs module could not be imported")
        try:
            with oqs.KeyEncapsulation(ALGORITHM) as kem:
                public_key = kem.generate_keypair()
                secret_key = kem.export_secret_key()
            return KyberKeypair(public_key=public_key, secret_key=secret_key)
        except Exception as e:
            raise ValueError(f"liboqs not available: {e}") from e

    def encapsulate(self, public_key: bytes) -> KyberEncapsulationResult:
        """Encapsulate a shared secret using the recipient's public key.

        Returns a (ciphertext, shared_secret) pair.  The ciphertext is sent to
        the recipient; the shared_secret is used locally as a key.
        """
        if not _OQS_AVAILABLE:
            raise ValueError("liboqs not available: oqs module could not be imported")
        try:
            with oqs.KeyEncapsulation(ALGORITHM) as kem:
                ciphertext, shared_secret = kem.encap_secret(public_key)
            return KyberEncapsulationResult(
                ciphertext=ciphertext,
                shared_secret=shared_secret,
            )
        except Exception as e:
            raise ValueError(f"liboqs not available: {e}") from e

    def decapsulate(self, ciphertext: bytes, secret_key: bytes) -> bytes:
        """Recover the shared secret from a ciphertext using the secret key."""
        if not _OQS_AVAILABLE:
            raise ValueError("liboqs not available: oqs module could not be imported")
        try:
            with oqs.KeyEncapsulation(ALGORITHM, secret_key=secret_key) as kem:
                return kem.decap_secret(ciphertext)
        except Exception as e:
            raise ValueError(f"liboqs not available: {e}") from e
