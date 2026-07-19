from __future__ import annotations

from cryptography.hazmat.primitives.cmac import CMAC
from cryptography.hazmat.primitives.ciphers import algorithms
from cryptography.hazmat.primitives.ciphers.aead import AESCCM


def aes_cmac(key: bytes, data: bytes) -> bytes:
    c = CMAC(algorithms.AES(key))
    c.update(data)
    return c.finalize()


def counter_bytes(counter: int) -> bytes:
    # Matches Kotlin Long.toBytes(): 8-byte little endian.
    return counter.to_bytes(8, "little", signed=False)


class SesameOS3Cipher:
    """Minimal port of SesameOS3BleCipher.

    Sesame OS3 uses AES-CCM with a 4-byte tag, AAD=00, and nonce:
    little-endian 8-byte counter + 00 + sesame token.
    """

    def __init__(self, session_key: bytes, sesame_token: bytes):
        self.session_key = session_key
        self.salt = b"\x00" + sesame_token
        self.encrypt_counter = 0
        self.decrypt_counter = 0
        self._aes = AESCCM(session_key, tag_length=4)

    def encrypt(self, plaintext: bytes) -> bytes:
        nonce = counter_bytes(self.encrypt_counter) + self.salt
        self.encrypt_counter += 1
        return self._aes.encrypt(nonce, plaintext, b"\x00")

    def decrypt(self, ciphertext: bytes) -> bytes:
        nonce = counter_bytes(self.decrypt_counter) + self.salt
        self.decrypt_counter += 1
        return self._aes.decrypt(nonce, ciphertext, b"\x00")
