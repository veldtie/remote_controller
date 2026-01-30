from __future__ import annotations

import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Dict, List

from .browsers import resolve_path
from .errors import CookieExportError
from .decrypt import decrypt_chrome_value, get_dpapi, load_local_state_key


def copy_db(db_path: Path) -> Path | None:
    try:
        handle = tempfile.NamedTemporaryFile(prefix="rc_cookies_", suffix=db_path.suffix, delete=False)
        temp_path = Path(handle.name)
        handle.close()
        shutil.copyfile(db_path, temp_path)
        return temp_path
    except Exception:
        return None


def extract_chrome_like(browser_name: str, config: Dict) -> List[Dict]:
    dpapi = get_dpapi()
    local_state_path = resolve_path(config.get("local_state")) if config.get("local_state") else None
    local_state_key = load_local_state_key(local_state_path, dpapi)
    cookies: List[Dict] = []
    found_any = False

    for base_path in config.get("cookie_paths", []):
        resolved = resolve_path(base_path)
        if not resolved or not resolved.exists():
            continue
        found_any = True
        temp_db = copy_db(resolved)
        if not temp_db:
            continue
        try:
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly
                FROM cookies
                """
            )
            for row in cursor.fetchall():
                value = row[2] or ""
                encrypted_value = row[3]
                if encrypted_value:
                    value = decrypt_chrome_value(encrypted_value, dpapi, local_state_key)
                cookies.append(
                    {
                        "browser": browser_name,
                        "domain": row[0],
                        "name": row[1],
                        "value": value,
                        "path": row[4],
                        "expires": row[5],
                        "secure": bool(row[6]),
                        "httponly": bool(row[7]),
                    }
                )
            conn.close()
        except Exception:
            pass
        finally:
            try:
                temp_db.unlink(missing_ok=True)
            except Exception:
                pass
    if not found_any:
        raise CookieExportError(
            "cookies_not_found",
            f"Cookies database not found for {browser_name}.",
        )
    return cookies
