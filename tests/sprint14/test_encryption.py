"""Sprint 14 — TokenEncryption unit tests (pure computation, no DB needed)."""
import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "../../services/integration-service"),
)

import pytest
from src.encryption import TokenEncryption


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def enc():
    return TokenEncryption("test-secret-key-for-testing-only")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTokenEncryption:
    def test_encrypt_returns_string(self, enc):
        """encrypt() must return a plain Python str."""
        result = enc.encrypt("hello")
        assert isinstance(result, str)

    def test_decrypt_roundtrip(self, enc):
        """Encrypt then decrypt returns the original plaintext."""
        plaintext = "my-secret-api-key"
        ciphertext = enc.encrypt(plaintext)
        assert enc.decrypt(ciphertext) == plaintext

    def test_different_plaintext_different_ciphertext(self, enc):
        """Two distinct inputs must produce distinct ciphertexts."""
        ct1 = enc.encrypt("alpha")
        ct2 = enc.encrypt("beta")
        assert ct1 != ct2

    def test_same_plaintext_different_ciphertext_each_time(self, enc):
        """Fernet is non-deterministic; encrypting the same string twice
        must yield two different ciphertexts (probabilistic assertion)."""
        ct1 = enc.encrypt("hello")
        ct2 = enc.encrypt("hello")
        # With Fernet's random IV the probability of collision is negligible
        assert ct1 != ct2

    def test_decrypt_wrong_key_returns_none(self, enc):
        """decrypt_safe() with a different key must return None, not raise."""
        ciphertext = enc.encrypt("super-secret")
        other_enc = TokenEncryption("other-key")
        assert other_enc.decrypt_safe(ciphertext) is None

    def test_decrypt_safe_on_invalid_returns_none(self, enc):
        """decrypt_safe() on arbitrary garbage must return None."""
        assert enc.decrypt_safe("this-is-not-a-valid-fernet-token") is None

    def test_empty_string_roundtrip(self, enc):
        """The empty string must encrypt and decrypt cleanly."""
        ciphertext = enc.encrypt("")
        assert enc.decrypt(ciphertext) == ""

    def test_long_token_roundtrip(self, enc):
        """A 512-character token must survive an encrypt/decrypt cycle."""
        long_token = "x" * 512
        ciphertext = enc.encrypt(long_token)
        assert enc.decrypt(ciphertext) == long_token
