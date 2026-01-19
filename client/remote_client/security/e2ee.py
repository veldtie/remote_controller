"""E2EE helpers for data channel payloads."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

E2EE_VERSION = 1
E2EE_PBKDF2_ITERS = 150_000
E2EE_SALT_PREFIX = "remote-controller:"


class E2EEError(ValueError):
    """Raised when E2EE payloads cannot be processed."""


def _b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def _derive_key(passphrase: str, session_id: str) -> bytes:
    if not passphrase:
        raise E2EEError("E2EE passphrase is missing.")
    salt = f"{E2EE_SALT_PREFIX}{session_id}".encode("utf-8")
    return hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8"),
        salt,
        E2EE_PBKDF2_ITERS,
        dklen=32,
    )


@dataclass(frozen=True)
class E2EEContext:
    """Holds derived E2EE keying material for a session."""

    _aesgcm: AESGCM
    session_id: str

    @classmethod
    def from_passphrase(cls, passphrase: str, session_id: str) -> "E2EEContext":
        key = _derive_key(passphrase, session_id)
        return cls(AESGCM(key), session_id)

    def encrypt_text(self, plaintext: str) -> str:
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        envelope = {
            "e2ee": E2EE_VERSION,
            "nonce": _b64encode(nonce),
            "ciphertext": _b64encode(ciphertext),
        }
        return json.dumps(envelope)

    def decrypt_envelope(self, envelope: dict[str, Any]) -> str:
        if not self.is_envelope(envelope):
            raise E2EEError("Missing E2EE envelope.")
        try:
            nonce = _b64decode(envelope["nonce"])
            ciphertext = _b64decode(envelope["ciphertext"])
        except (KeyError, ValueError) as exc:
            raise E2EEError("Invalid E2EE payload.") from exc
        try:
            plaintext = self._aesgcm.decrypt(nonce, ciphertext, None)
        except InvalidTag as exc:
            raise E2EEError("E2EE authentication failed.") from exc
        return plaintext.decode("utf-8")

    @staticmethod
    def is_envelope(payload: dict[str, Any]) -> bool:
        return (
            payload.get("e2ee") == E2EE_VERSION
            and "nonce" in payload
            and "ciphertext" in payload
        )


def load_e2ee_context(session_id: str) -> E2EEContext | None:
    """Create an E2EE context from environment configuration."""
    passphrase = os.getenv("RC_E2EE_PASSPHRASE") or os.getenv("RC_E2EE_KEY")
    if not passphrase:
        return None
    return E2EEContext.from_passphrase(passphrase.strip(), session_id)
