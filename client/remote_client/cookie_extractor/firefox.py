from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List

from .browsers import resolve_path
from .errors import CookieExportError
from .extractors import copy_db


def get_firefox_cookie_paths() -> List[Path]:
    profiles_path = resolve_path(Path("APPDATA") / "Mozilla" / "Firefox" / "Profiles")
    if not profiles_path or not profiles_path.exists():
        return []
    paths: List[Path] = []
    for profile in profiles_path.iterdir():
        if not profile.is_dir():
            continue
        cookie_file = profile / "cookies.sqlite"
        if cookie_file.exists():
            paths.append(cookie_file)
    return paths


def extract_firefox() -> List[Dict]:
    cookies: List[Dict] = []
    paths = get_firefox_cookie_paths()
    if not paths:
        raise CookieExportError(
            "cookies_not_found",
            "Firefox cookies database not found.",
        )
    for db_path in paths:
        temp_db = copy_db(db_path)
        if not temp_db:
            continue
        try:
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT host, name, value, path, expiry, isSecure, isHttpOnly
                FROM moz_cookies
                """
            )
            profile_name = db_path.parent.name
            for row in cursor.fetchall():
                cookies.append(
                    {
                        "browser": "firefox",
                        "profile": profile_name,
                        "domain": row[0],
                        "name": row[1],
                        "value": row[2],
                        "path": row[3],
                        "expires": row[4],
                        "secure": bool(row[5]),
                        "httponly": bool(row[6]),
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
    return cookies
