from __future__ import annotations

import base64
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Optional[Fernet]:
    key = os.environ.get("SECRET_KEY", "").strip()
    if not key:
        return None
    # Accept either a pre-generated Fernet key (urlsafe base64 32 bytes)
    # or a raw 32-byte key (hex/base64), we normalize to Fernet format if needed.
    try:
        # If looks like a Fernet key already
        if len(key) >= 43:
            return Fernet(key)
        # If ascii/plain, pad to 32 bytes then base64-url encode
        raw = key.encode("utf-8")
        raw = (raw + b"0" * 32)[:32]
        fkey = base64.urlsafe_b64encode(raw)
        return Fernet(fkey)
    except Exception:
        return None


def encrypt_text(plaintext: str) -> str:
    f = _get_fernet()
    if not f:
        # If no key, return plaintext prefixed (dev mode fallback)
        return f"plain:{plaintext}"
    token = f.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    return f"enc:{token}"


def decrypt_text(ciphertext: str) -> str:
    if ciphertext.startswith("plain:"):
        return ciphertext.split(":", 1)[1]
    if not ciphertext.startswith("enc:"):
        return ciphertext
    token = ciphertext.split(":", 1)[1]
    f = _get_fernet()
    if not f:
        # No key available; cannot decrypt
        raise InvalidToken("No SECRET_KEY for decryption")
    return f.decrypt(token.encode("utf-8")).decode("utf-8")
