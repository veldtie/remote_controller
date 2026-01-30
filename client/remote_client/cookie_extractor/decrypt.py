from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import CookieExportError

_LOCAL_STATE_CACHE: dict[str, bytes | None] = {}


def get_dpapi() -> Any:
    if os.name != "nt":
        raise CookieExportError("unsupported", "Cookie export is only supported on Windows.")
    try:
        import win32crypt  # type: ignore
    except Exception as exc:
        raise CookieExportError(
            "missing_dependency", "win32crypt is not available."
        ) from exc
    return win32crypt


def load_local_state_key(local_state_path: Path | None, dpapi: Any | None = None) -> bytes | None:
    if not local_state_path or not local_state_path.exists():
        return None
    cache_key = str(local_state_path)
    if cache_key in _LOCAL_STATE_CACHE:
        return _LOCAL_STATE_CACHE[cache_key]
    try:
        raw = local_state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        encrypted_key_b64 = data["os_crypt"]["encrypted_key"]
    except Exception:
        _LOCAL_STATE_CACHE[cache_key] = None
        return None
    try:
        encrypted_key = base64.b64decode(encrypted_key_b64)
    except Exception:
        _LOCAL_STATE_CACHE[cache_key] = None
        return None
    if encrypted_key.startswith(b"DPAPI"):
        encrypted_key = encrypted_key[5:]
    if dpapi is None:
        dpapi = get_dpapi()
    try:
        key = dpapi.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
    except Exception:
        key = None
    _LOCAL_STATE_CACHE[cache_key] = key
    return key


def decrypt_chrome_value(
    encrypted_value: bytes | memoryview,
    dpapi: Any,
    local_state_key: bytes | None,
) -> str:
    if isinstance(encrypted_value, memoryview):
        encrypted_bytes = encrypted_value.tobytes()
    else:
        encrypted_bytes = bytes(encrypted_value)
    if not encrypted_bytes:
        return ""
    if encrypted_bytes.startswith((b"v10", b"v11", b"v12")):
        if local_state_key:
            nonce = encrypted_bytes[3:15]
            ciphertext = encrypted_bytes[15:]
            try:
                decrypted = AESGCM(local_state_key).decrypt(nonce, ciphertext, None)
                return decrypted.decode("utf-8", errors="replace")
            except Exception:
                pass
    try:
        decrypted = dpapi.CryptUnprotectData(encrypted_bytes, None, None, None, 0)[1]
        return decrypted.decode("utf-8", errors="replace")
    except Exception:
        return "[decrypt_failed]"
