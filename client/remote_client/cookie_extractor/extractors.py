from __future__ import annotations

import logging
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from .browsers import resolve_path
from .errors import CookieExportError
from .decrypt import decrypt_chrome_value, get_dpapi, load_local_state_key, _get_abe_decryptor

logger = logging.getLogger(__name__)


def copy_db(db_path: Path) -> Path | None:
    try:
        handle = tempfile.NamedTemporaryFile(prefix="rc_cookies_", suffix=db_path.suffix, delete=False)
        temp_path = Path(handle.name)
        handle.close()
        shutil.copyfile(db_path, temp_path)
        return temp_path
    except Exception:
        return None


def _check_abe_support(local_state_path: Optional[Path]) -> Dict:
    """Check App-Bound Encryption support status."""
    result = {
        "detected": False,
        "available": False,
        "method": None,
    }
    
    if not local_state_path:
        return result
    
    try:
        from .app_bound_encryption import check_abe_support, is_abe_encrypted_key
        import json
        import base64
        
        # Check if Local State contains ABE key
        try:
            raw = local_state_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            encrypted_key_b64 = data["os_crypt"]["encrypted_key"]
            encrypted_key = base64.b64decode(encrypted_key_b64)
            result["detected"] = is_abe_encrypted_key(encrypted_key)
        except Exception:
            pass
        
        # Check system support
        support = check_abe_support()
        result.update(support)
        
    except ImportError:
        pass
    
    return result


def extract_chrome_like(browser_name: str, config: Dict) -> List[Dict]:
    """
    Extract cookies from Chrome-like browsers.
    
    Supports:
    - Standard DPAPI encryption (Chrome < 127)
    - App-Bound Encryption (Chrome 127+)
    - Multiple encryption versions (v10, v11, v12, v20)
    """
    dpapi = get_dpapi()
    local_state_path = resolve_path(config.get("local_state")) if config.get("local_state") else None
    
    # Check ABE support and log status
    abe_status = _check_abe_support(local_state_path)
    if abe_status.get("detected"):
        logger.info(
            "App-Bound Encryption detected for %s. ABE support: %s",
            browser_name,
            "available" if abe_status.get("dpapi_available") else "limited"
        )
    
    # Load encryption key (handles both DPAPI and ABE)
    local_state_key = load_local_state_key(local_state_path, dpapi)
    
    # Get ABE decryptor for v20 values
    abe_decryptor = _get_abe_decryptor(local_state_path)
    
    cookies: List[Dict] = []
    found_any = False
    decrypt_stats = {"success": 0, "failed": 0, "abe_failed": 0}

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
                    decrypted = decrypt_chrome_value(
                        encrypted_value, 
                        dpapi, 
                        local_state_key,
                        abe_decryptor
                    )
                    if decrypted.startswith("[") and decrypted.endswith("_failed]"):
                        decrypt_stats["failed"] += 1
                        if "abe" in decrypted:
                            decrypt_stats["abe_failed"] += 1
                    else:
                        decrypt_stats["success"] += 1
                    value = decrypted
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
        except Exception as e:
            logger.debug("Error reading cookies database for %s: %s", browser_name, e)
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
    
    # Log decryption statistics
    total = decrypt_stats["success"] + decrypt_stats["failed"]
    if total > 0:
        logger.info(
            "%s cookie decryption: %d/%d successful, %d ABE failures",
            browser_name,
            decrypt_stats["success"],
            total,
            decrypt_stats["abe_failed"]
        )
    
    return cookies
