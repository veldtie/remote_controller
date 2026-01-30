from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Dict, Iterable, List

from .browsers import BROWSER_CONFIG
from .errors import CookieExportError
from .extractors import extract_chrome_like
from .firefox import extract_firefox


def _normalize_browsers(value: Iterable[str] | str | None) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    normalized: List[str] = []
    for item in value:
        name = str(item).strip().lower()
        if not name:
            continue
        if name in {"all", "*"}:
            continue
        normalized.append(name)
    return list(dict.fromkeys(normalized))


class CookieExporter:
    def export_payload(self, browsers: Iterable[str] | str | None = None) -> Dict:
        requested = _normalize_browsers(browsers)
        if not requested:
            requested = list(BROWSER_CONFIG.keys())
        cookies: List[Dict] = []
        errors: List[Dict] = []

        for browser_name in requested:
            config = BROWSER_CONFIG.get(browser_name)
            if not config:
                errors.append(
                    {
                        "browser": browser_name,
                        "code": "unsupported_browser",
                        "message": "Unsupported browser",
                    }
                )
                continue
            try:
                if config.get("type") == "chromium":
                    cookies.extend(extract_chrome_like(browser_name, config))
                elif config.get("type") == "firefox":
                    cookies.extend(extract_firefox())
                else:
                    errors.append(
                        {
                            "browser": browser_name,
                            "code": "unsupported_browser",
                            "message": "Unsupported browser type",
                        }
                    )
            except CookieExportError as exc:
                errors.append(
                    {
                        "browser": browser_name,
                        "code": exc.code,
                        "message": str(exc),
                    }
                )
            except Exception as exc:
                errors.append(
                    {
                        "browser": browser_name,
                        "code": "export_failed",
                        "message": str(exc),
                    }
                )

        if not cookies:
            if errors:
                summary = "; ".join(
                    f"{entry.get('browser')}: {entry.get('message')}"
                    for entry in errors
                    if entry.get("browser")
                )
                raise CookieExportError(
                    "cookies_empty",
                    f"No cookies extracted. {summary}",
                )
            raise CookieExportError(
                "cookies_empty",
                "No cookies found for selected browsers.",
            )

        payload: Dict[str, object] = {
            "version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "count": len(cookies),
            "browsers": requested,
            "cookies": cookies,
        }
        if errors:
            payload["errors"] = errors
        return payload

    def export_base64(self, browsers: Iterable[str] | str | None = None) -> str:
        payload = self.export_payload(browsers)
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return base64.b64encode(raw).decode("ascii")
