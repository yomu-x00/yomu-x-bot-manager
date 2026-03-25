"""Tests for AES-GCM encryption utilities."""

import base64

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import pytest

from crypto import encrypt, decrypt, generate_key


@pytest.fixture
def test_key():
    """Generate a test encryption key."""
    raw = AESGCM.generate_key(bit_length=256)
    return raw


def test_encrypt_decrypt_roundtrip(test_key):
    """Encrypting then decrypting should return the original text."""
    plaintext = "secret_auth_token_12345"
    encrypted = encrypt(plaintext, key=test_key)
    decrypted = decrypt(encrypted, key=test_key)
    assert decrypted == plaintext


def test_encrypt_produces_different_ciphertexts(test_key):
    """Same plaintext should produce different ciphertexts (random nonce)."""
    plaintext = "same_text"
    ct1 = encrypt(plaintext, key=test_key)
    ct2 = encrypt(plaintext, key=test_key)
    assert ct1 != ct2


def test_decrypt_with_wrong_key(test_key):
    """Decrypting with a wrong key should raise an error."""
    wrong_key = AESGCM.generate_key(bit_length=256)
    encrypted = encrypt("secret", key=test_key)
    with pytest.raises(Exception):
        decrypt(encrypted, key=wrong_key)


def test_generate_key_is_valid_base64():
    """Generated key should be valid base64 and 32 bytes when decoded."""
    key_b64 = generate_key()
    raw = base64.b64decode(key_b64)
    assert len(raw) == 32


def test_encrypt_empty_string(test_key):
    """Should handle empty string."""
    encrypted = encrypt("", key=test_key)
    decrypted = decrypt(encrypted, key=test_key)
    assert decrypted == ""


def test_encrypt_unicode(test_key):
    """Should handle unicode text."""
    plaintext = "日本語テスト 🎉"
    encrypted = encrypt(plaintext, key=test_key)
    decrypted = decrypt(encrypted, key=test_key)
    assert decrypted == plaintext
