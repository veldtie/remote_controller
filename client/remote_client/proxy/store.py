"""In-memory proxy settings store."""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional


@dataclass(frozen=True)
class ProxySettings:
    host: str
    port: int
    username: str = ""
    password: str = ""
    proxy_type: str = "http"

    def to_text(self) -> str:
        return "\n".join(
            [
                f"type={self.proxy_type}",
                f"host={self.host}",
                f"port={self.port}",
                f"username={self.username}",
                f"password={self.password}",
            ]
        )


_proxy_settings: Optional[ProxySettings] = None


def set_proxy_settings(settings: ProxySettings | None) -> None:
    global _proxy_settings
    _proxy_settings = settings


def get_proxy_settings() -> Optional[ProxySettings]:
    return _proxy_settings


def load_proxy_settings_from_env() -> Optional[ProxySettings]:
    host = os.getenv("RC_PROXY_HOST", "").strip()
    port_raw = os.getenv("RC_PROXY_PORT", "").strip()
    if not host or not port_raw:
        return None
    try:
        port = int(port_raw)
    except ValueError:
        return None
    if port <= 0 or port > 65535:
        return None
    username = os.getenv("RC_PROXY_USER", "").strip()
    password = os.getenv("RC_PROXY_PASS", "").strip()
    proxy_type = os.getenv("RC_PROXY_TYPE", "").strip() or "http"
    return ProxySettings(
        host=host,
        port=port,
        username=username,
        password=password,
        proxy_type=proxy_type,
    )
