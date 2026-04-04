"""
CRYSTALS-Dilithium3 Digital Signatures

Uses liboqs-python (Open Quantum Safe).
Dilithium3 is NIST PQC Level 3.

Key operations:
- generate_keypair() → (public_key: bytes, secret_key: bytes)
- sign(message: bytes, secret_key: bytes) → signature: bytes
- verify(message: bytes, signature: bytes, public_key: bytes) → bool
"""

import hashlib
from dataclasses import dataclass, field

try:
    import oqs  # liboqs-python
    _OQS_AVAILABLE = True
except ImportError:
    _OQS_AVAILABLE = False
    oqs = None  # type: ignore[assignment]

ALGORITHM = "Dilithium3"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DilithiumKeypair:
    public_key: bytes
    secret_key: bytes
    algorithm: str = ALGORITHM
    fingerprint: bytes = field(init=False)  # SHA-256 of public_key

    def __post_init__(self):
        self.fingerprint = hashlib.sha256(self.public_key).digest()


class InvalidSignatureError(Exception):
    """Raised when a Dilithium signature fails verification."""


# ---------------------------------------------------------------------------
# Signer
# ---------------------------------------------------------------------------

class DilithiumSigner:
    """Wrapper around liboqs Dilithium3 signature operations.

    All methods raise ValueError if liboqs is not available or if the
    underlying OQS call fails unexpectedly.  verify() never raises for an
    invalid signature — it returns False instead.
    """

    def generate_keypair(self) -> DilithiumKeypair:
        """Generate a fresh Dilithium3 keypair."""
        if not _OQS_AVAILABLE:
            raise ValueError("liboqs not available: oqs module could not be imported")
        try:
            with oqs.Signature(ALGORITHM) as sig:
                public_key = sig.generate_keypair()
                secret_key = sig.export_secret_key()
            return DilithiumKeypair(public_key=public_key, secret_key=secret_key)
        except Exception as e:
            raise ValueError(f"liboqs not available: {e}") from e

    def sign(self, message: bytes, secret_key: bytes) -> bytes:
        """Sign a message with the given secret key.

        Returns the raw Dilithium3 signature bytes.
        """
        if not _OQS_AVAILABLE:
            raise ValueError("liboqs not available: oqs module could not be imported")
        try:
            with oqs.Signature(ALGORITHM, secret_key=secret_key) as sig:
                return sig.sign(message)
        except Exception as e:
            raise ValueError(f"liboqs not available: {e}") from e

    def verify(self, message: bytes, signature: bytes, public_key: bytes) -> bool:
        """Verify a Dilithium3 signature.

        Returns True if valid.  Never raises — returns False on any error,
        including invalid signatures, wrong key sizes, and liboqs failures.
        """
        if not _OQS_AVAILABLE:
            return False
        try:
            with oqs.Signature(ALGORITHM) as sig:
                return sig.verify(message, signature, public_key)
        except Exception:
            return False
