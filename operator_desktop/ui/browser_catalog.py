from __future__ import annotations

import re


DEFAULT_BROWSERS: list[dict[str, str]] = [
    {"id": "chrome", "name": "Chrome"},
    {"id": "safari", "name": "Safari"},
    {"id": "edge", "name": "Edge"},
    {"id": "firefox", "name": "Firefox"},
    {"id": "samsung_internet", "name": "Samsung Internet"},
    {"id": "opera", "name": "Opera"},
    {"id": "brave", "name": "Brave"},
    {"id": "uc_browser", "name": "UC Browser"},
    {"id": "huawei_browser", "name": "Huawei Browser"},
    {"id": "dolphin_anty", "name": "Dolphin Anty"},
    {"id": "octo", "name": "Octo Browser"},
    {"id": "adspower", "name": "AdsPower"},
    {"id": "linken_sphere_2", "name": "Linken Sphere 2"},
]

EXCLUDED_BROWSER_IDS = {"yandex"}


def _normalize_browser_id(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = text.replace("&", "and")
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text


def _normalize_browser_entries(value: object) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key, version in value.items():
            name = str(key or "").strip()
            if not name:
                continue
            browser_id = _normalize_browser_id(name)
            if not browser_id:
                continue
            entry = {"id": browser_id, "name": name}
            version_text = str(version or "").strip()
            if version_text:
                entry["version"] = version_text
            entries.append(entry)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                browser_id = _normalize_browser_id(
                    item.get("id")
                    or item.get("key")
                    or item.get("name")
                    or item.get("browser")
                )
                name = str(item.get("name") or item.get("browser") or "").strip()
                if not name:
                    name = browser_id.replace("_", " ").title() if browser_id else ""
                if not browser_id or not name:
                    continue
                entry = {"id": browser_id, "name": name}
                version_text = str(item.get("version") or item.get("ver") or "").strip()
                if version_text:
                    entry["version"] = version_text
                entries.append(entry)
            else:
                name = str(item or "").strip()
                if not name:
                    continue
                browser_id = _normalize_browser_id(name)
                if not browser_id:
                    continue
                entries.append({"id": browser_id, "name": name})
    return entries


def browser_choices_from_config(config: object) -> list[tuple[str, str]]:
    browsers = None
    has_browsers_key = False
    if isinstance(config, dict):
        has_browsers_key = "browsers" in config
        browsers = config.get("browsers")
    entries = _normalize_browser_entries(browsers)
    if not entries:
        if has_browsers_key:
            return []
        entries = [dict(item) for item in DEFAULT_BROWSERS]
    seen: set[str] = set()
    choices: list[tuple[str, str]] = []
    for entry in entries:
        browser_id = str(entry.get("id") or "").strip()
        name = str(entry.get("name") or "").strip()
        if not browser_id or not name or browser_id in seen or browser_id in EXCLUDED_BROWSER_IDS:
            continue
        seen.add(browser_id)
        choices.append((browser_id, name))
    return choices


def browser_keys_from_config(config: object) -> list[str]:
    return [browser_id for browser_id, _ in browser_choices_from_config(config)]
