"""Anti-fraud heuristics for region-based checks on Windows."""
from __future__ import annotations

import ctypes
import ipaddress
import locale
import os
import platform
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from geoip2.database import Reader as GeoReader
    from geoip2.errors import AddressNotFoundError
except ImportError:  # pragma: no cover - optional dependency
    GeoReader = None
    AddressNotFoundError = Exception


CIS_COUNTRY_CODES = {
    "AM",
    "AZ",
    "BY",
    "GE",
    "KZ",
    "KG",
    "MD",
    "RU",
    "TJ",
    "TM",
    "UA",
    "UZ",
}

DEFAULT_BLOCKED_COUNTRIES = set(CIS_COUNTRY_CODES) | {"CN", "IN"}

CIS_LANGUAGE_CODES = {
    "ru",
    "uk",
    "be",
    "kk",
    "ky",
    "tg",
    "tk",
    "uz",
    "az",
    "hy",
    "ka",
    "mo",
}
CHINA_LANGUAGE_CODES = {"zh"}
INDIA_LANGUAGE_CODES = {
    "hi",
    "bn",
    "ta",
    "te",
    "mr",
    "gu",
    "kn",
    "ml",
    "pa",
    "ur",
    "or",
    "as",
}

CIS_TIMEZONES = {
    "Russian Standard Time",
    "Kaliningrad Standard Time",
    "Astrakhan Standard Time",
    "Saratov Standard Time",
    "Ulyanovsk Standard Time",
    "Volgograd Standard Time",
    "Ekaterinburg Standard Time",
    "West Asia Standard Time",
    "Central Asia Standard Time",
    "West Siberian Standard Time",
    "North Asia Standard Time",
    "North Asia East Standard Time",
    "Yakutsk Standard Time",
    "Vladivostok Standard Time",
    "Magadan Standard Time",
    "Sakhalin Standard Time",
    "Kamchatka Standard Time",
    "Transbaikal Standard Time",
    "Altai Standard Time",
    "Tomsk Standard Time",
    "Novosibirsk Standard Time",
    "Caucasus Standard Time",
    "Belarus Standard Time",
    "Georgian Standard Time",
    "Armenian Standard Time",
    "Azerbaijan Standard Time",
}
CHINA_TIMEZONES = {"China Standard Time"}
INDIA_TIMEZONES = {"India Standard Time"}


@dataclass(frozen=True)
class RegionFraudResult:
    is_suspicious: bool
    score: int
    threshold: int
    indicators: tuple[str, ...]


def _split_locale(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    value = value.replace("-", "_")
    parts = value.split("_")
    language = parts[0].lower() if parts else None
    country = parts[1].upper() if len(parts) > 1 else None
    return language, country


def _get_user_default_locale_name() -> str | None:
    if platform.system() != "Windows":
        return None
    try:
        kernel32 = ctypes.windll.kernel32
    except AttributeError:
        return None
    buffer = ctypes.create_unicode_buffer(85)
    if kernel32.GetUserDefaultLocaleName(buffer, len(buffer)):
        return buffer.value
    return None


def _get_user_default_geo_name() -> str | None:
    if platform.system() != "Windows":
        return None
    try:
        kernel32 = ctypes.windll.kernel32
    except AttributeError:
        return None
    buffer = ctypes.create_unicode_buffer(16)
    if kernel32.GetUserDefaultGeoName(buffer, len(buffer)):
        return buffer.value.upper()
    return None


def _get_ui_language_locale() -> str | None:
    if platform.system() != "Windows":
        return None
    try:
        lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except AttributeError:
        return None
    return locale.windows_locale.get(lcid)


def _get_timezone_name() -> str | None:
    try:
        output = subprocess.check_output(
            ["tzutil", "/g"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return output.strip()


def _get_public_ip() -> str | None:
    for url in ("https://api.ipify.org", "https://icanhazip.com"):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                value = response.read().decode("utf-8").strip()
        except OSError:
            continue
        try:
            ipaddress.ip_address(value)
        except ValueError:
            continue
        return value
    return None


def _resolve_geo_db_path() -> Path | None:
    env_path = os.getenv("RC_GEOIP_DB")
    if env_path:
        path = Path(env_path).expanduser()
        if path.exists():
            return path
    base_dirs = []
    if getattr(sys, "frozen", False):
        base_dirs.append(Path(sys.executable).resolve().parent)
    base_dirs.append(Path(__file__).resolve().parent)
    base_dirs.append(Path(__file__).resolve().parent.parent)
    for base_dir in base_dirs:
        for candidate in (
            base_dir / "GeoLite2-Country.mmdb",
            base_dir / "geoip.mmdb",
            base_dir / "data" / "GeoLite2-Country.mmdb",
        ):
            if candidate.exists():
                return candidate
    return None


def _lookup_country(ip_address: str | None) -> str | None:
    if not ip_address or GeoReader is None:
        return None
    db_path = _resolve_geo_db_path()
    if not db_path:
        return None
    try:
        reader = GeoReader(str(db_path))
    except Exception:
        return None
    try:
        response = reader.country(ip_address)
        return response.country.iso_code
    except (AddressNotFoundError, ValueError):
        return None
    finally:
        reader.close()


def _resolve_region_flags(blocked_countries: set[str]) -> tuple[bool, bool, bool]:
    has_cis = bool(blocked_countries & CIS_COUNTRY_CODES)
    has_cn = "CN" in blocked_countries
    has_in = "IN" in blocked_countries
    return has_cis, has_cn, has_in


def analyze_region(blocked_countries: Iterable[str] | None = None) -> RegionFraudResult:
    if platform.system() != "Windows":
        return RegionFraudResult(is_suspicious=False, score=0, threshold=0, indicators=())

    blocked = {code.upper() for code in (blocked_countries or DEFAULT_BLOCKED_COUNTRIES) if code}
    if not blocked:
        return RegionFraudResult(is_suspicious=False, score=0, threshold=0, indicators=())

    ip_weight = 6
    geo_weight = 4
    locale_weight = 3
    lang_weight = 2
    tz_weight = 2
    threshold = 6

    indicators: list[str] = []
    score = 0

    public_ip = _get_public_ip()
    ip_country = _lookup_country(public_ip)
    if ip_country and ip_country.upper() in blocked:
        score += ip_weight
        indicators.append(f"ip_country:{ip_country}")

    geo_country = _get_user_default_geo_name()
    if geo_country and geo_country in blocked:
        score += geo_weight
        indicators.append(f"geo_region:{geo_country}")

    locale_name = _get_user_default_locale_name()
    _, locale_country = _split_locale(locale_name)
    if not locale_country:
        locale_name = locale.getdefaultlocale()[0] if locale.getdefaultlocale() else None
        _, locale_country = _split_locale(locale_name)
    if locale_country and locale_country in blocked:
        score += locale_weight
        indicators.append(f"locale_region:{locale_country}")

    ui_locale = _get_ui_language_locale()
    ui_lang, _ = _split_locale(ui_locale)
    if not ui_lang:
        sys_lang = locale.getlocale()[0]
        ui_lang, _ = _split_locale(sys_lang)

    has_cis, has_cn, has_in = _resolve_region_flags(blocked)
    language_flags = set()
    if has_cis:
        language_flags |= CIS_LANGUAGE_CODES
    if has_cn:
        language_flags |= CHINA_LANGUAGE_CODES
    if has_in:
        language_flags |= INDIA_LANGUAGE_CODES
    if ui_lang and ui_lang in language_flags:
        score += lang_weight
        indicators.append(f"ui_lang:{ui_lang}")

    timezone_name = _get_timezone_name()
    tz_flags = set()
    if has_cis:
        tz_flags |= CIS_TIMEZONES
    if has_cn:
        tz_flags |= CHINA_TIMEZONES
    if has_in:
        tz_flags |= INDIA_TIMEZONES
    if timezone_name and timezone_name in tz_flags:
        score += tz_weight
        indicators.append(f"timezone:{timezone_name}")

    suspicious = score >= threshold
    return RegionFraudResult(
        is_suspicious=suspicious,
        score=score,
        threshold=threshold,
        indicators=tuple(indicators),
    )
