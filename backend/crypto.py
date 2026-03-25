"""AES-GCM encryption for sensitive credential storage."""

import os
import base64

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def get_encryption_key() -> bytes:
    """Get the encryption key from environment variable."""
    key_b64 = os.environ.get("ENCRYPTION_KEY", "")
    if not key_b64:
        raise RuntimeError("ENCRYPTION_KEY environment variable is not set")
    return base64.b64decode(key_b64)


def generate_key() -> str:
    """Generate a new AES-256 key and return as base64 string."""
    key = AESGCM.generate_key(bit_length=256)
    return base64.b64encode(key).decode()


def encrypt(plaintext: str, key: bytes | None = None) -> str:
    """Encrypt a string with AES-GCM. Returns base64(nonce + ciphertext)."""
    if key is None:
        key = get_encryption_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt(token: str, key: bytes | None = None) -> str:
    """Decrypt a base64(nonce + ciphertext) string with AES-GCM."""
    if key is None:
        key = get_encryption_key()
    data = base64.b64decode(token)
    nonce = data[:12]
    ciphertext = data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode()
