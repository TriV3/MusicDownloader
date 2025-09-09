import os
from backend.app.utils.crypto import encrypt_text, decrypt_text


def test_encrypt_decrypt_with_key(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "supersecretkey1234567890123456")
    ct = encrypt_text("hello")
    assert ct.startswith("enc:")
    pt = decrypt_text(ct)
    assert pt == "hello"


def test_encrypt_decrypt_without_key(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    ct = encrypt_text("hello")
    assert ct.startswith("plain:")
    # decrypt without key returns plaintext part
    assert decrypt_text(ct) == "hello"