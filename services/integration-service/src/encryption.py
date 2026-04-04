from cryptography.fernet import Fernet
import base64
import hashlib


class TokenEncryption:
    def __init__(self, key: str):
        # Derive a valid Fernet key from the config string
        key_bytes = hashlib.sha256(key.encode()).digest()
        self.fernet = Fernet(base64.urlsafe_b64encode(key_bytes))

    def encrypt(self, plaintext: str) -> str:
        return self.fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self.fernet.decrypt(ciphertext.encode()).decode()

    def decrypt_safe(self, ciphertext: str) -> str | None:
        """Returns None instead of raising on decryption failure."""
        try:
            return self.decrypt(ciphertext)
        except Exception:
            return None
