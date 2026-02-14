"""SOCKS5 proxy lifecycle management and host resolution helpers."""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import socket
import threading
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

from remote_client.config import resolve_signaling_token, resolve_signaling_url

from .socks5_server import Socks5ProxyServer
from .store import ProxySettings, get_proxy_settings, set_proxy_settings


logger = logging.getLogger("remote_client.proxy")


def _read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _socks5_enabled() -> bool:
    value = os.getenv("RC_SOCKS5_DISABLE", "")
    return value.strip().lower() not in {"1", "true", "yes", "on"}


def _socks5_udp_enabled() -> bool:
    value = os.getenv("RC_SOCKS5_UDP", "1")
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _is_unusable_host(value: str | None) -> bool:
    if not value:
        return True
    lowered = value.strip().lower()
    return lowered in {"0.0.0.0", "127.0.0.1", "::", "::1"}


def _is_usable_ip(value: str) -> bool:
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (addr.is_loopback or addr.is_link_local)


def _resolve_primary_ip() -> str | None:
    try:
        hostname = socket.gethostname()
        for family, _type, _proto, _canon, sockaddr in socket.getaddrinfo(hostname, None):
            if family in {socket.AF_INET, socket.AF_INET6}:
                candidate = sockaddr[0]
                if _is_usable_ip(candidate):
                    return candidate
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            candidate = sock.getsockname()[0]
            if _is_usable_ip(candidate):
                return candidate
    except OSError:
        pass
    return None


def _build_public_ip_url(base_url: str, token: str | None) -> str | None:
    if not base_url:
        return None
    if "://" not in base_url:
        base_url = f"http://{base_url}"
    parsed = urllib.parse.urlsplit(base_url)
    scheme = parsed.scheme
    if scheme in {"ws", "wss"}:
        scheme = "https" if scheme == "wss" else "http"
    query = urllib.parse.urlencode({"token": token}) if token else ""
    return urllib.parse.urlunsplit((scheme, parsed.netloc, "/public-ip", query, ""))


def _fetch_public_ip(base_url: str | None, token: str | None) -> str | None:
    if not base_url:
        return None
    url = _build_public_ip_url(base_url, token)
    if not url:
        return None
    headers: dict[str, str] = {}
    if token:
        headers["x-rc-token"] = token
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    ip_value = payload.get("ip") if isinstance(payload, dict) else None
    if not isinstance(ip_value, str):
        return None
    cleaned = ip_value.strip()
    return cleaned or None


def resolve_proxy_export_host(
    bind_host: str,
    public_host: str | None = None,
    allow_public_ip_lookup: bool = True,
) -> str | None:
    candidate = (public_host or "").strip() or None
    if not candidate:
        env_public = os.getenv("RC_SOCKS5_PUBLIC_HOST", "").strip()
        if not env_public:
            env_public = os.getenv("RC_PROXY_HOST", "").strip()
        candidate = env_public or None
    if not candidate and allow_public_ip_lookup:
        candidate = _fetch_public_ip(resolve_signaling_url(), resolve_signaling_token())
    if candidate and not _is_unusable_host(candidate):
        return candidate
    if bind_host and not _is_unusable_host(bind_host):
        return bind_host
    return _resolve_primary_ip()


@dataclass
class ProxyRuntime:
    server: Socks5ProxyServer
    bind_host: str
    udp: bool
    export_host: str | None
    settings_applied: bool
    previous_settings: ProxySettings | None

    @property
    def port(self) -> int:
        return self.server.port


class ProxyServerManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runtime: ProxyRuntime | None = None

    def runtime(self) -> ProxyRuntime | None:
        return self._runtime

    def payload(self) -> dict | None:
        runtime = self._runtime
        if not runtime:
            return None
        payload = {
            "enabled": True,
            "type": "socks5",
            "port": runtime.port,
            "udp": runtime.udp,
        }
        if runtime.export_host:
            payload["host"] = runtime.export_host
        return payload

    def start(
        self,
        bind_host: str = "0.0.0.0",
        port: int = 1080,
        udp: bool = True,
        public_host: str | None = None,
        allow_public_ip_lookup: bool = True,
        force: bool = False,
        strict_port: bool = False,
    ) -> ProxyRuntime | None:
        if not _socks5_enabled():
            return None
        bind_host = (bind_host or "0.0.0.0").strip() or "0.0.0.0"
        try:
            port_value = int(port)
        except (TypeError, ValueError):
            port_value = 1080
        if port_value <= 0 or port_value > 65535:
            logger.warning("Invalid RC_SOCKS5_PORT=%s; falling back to 1080.", port_value)
            port_value = 1080
        if strict_port and port_value == 0:
            logger.warning("Strict proxy port requested with port=0; refusing to start.")
            return None
        udp_value = bool(udp)
        with self._lock:
            if self._runtime and not force:
                return self._runtime
            if self._runtime:
                self._stop_locked()
            server = Socks5ProxyServer(
                host=bind_host,
                port=port_value,
                enable_udp=udp_value,
            )
            try:
                server.start()
            except OSError as exc:
                if strict_port:
                    logger.warning(
                        "SOCKS5 proxy port %s unavailable (strict): %s",
                        port_value,
                        exc,
                    )
                    return None
                logger.warning(
                    "SOCKS5 proxy port %s unavailable, selecting random port: %s",
                    port_value,
                    exc,
                )
                server = Socks5ProxyServer(
                    host=bind_host,
                    port=0,
                    enable_udp=udp_value,
                )
                server.start()
            export_host = resolve_proxy_export_host(
                bind_host,
                public_host=public_host,
                allow_public_ip_lookup=allow_public_ip_lookup,
            )
            if export_host and _is_unusable_host(export_host):
                logger.warning(
                    "SOCKS5 proxy export host %s may be unreachable; set RC_SOCKS5_PUBLIC_HOST to override.",
                    export_host,
                )
                export_host = None
            if not export_host:
                logger.warning(
                    "SOCKS5 proxy export host unresolved; set RC_SOCKS5_PUBLIC_HOST to advertise a reachable address."
                )
            previous_settings: ProxySettings | None = None
            settings_applied = False
            if export_host:
                previous_settings = get_proxy_settings()
                set_proxy_settings(
                    ProxySettings(
                        host=export_host,
                        port=server.port,
                        proxy_type="socks5",
                    )
                )
                settings_applied = True
            runtime = ProxyRuntime(
                server=server,
                bind_host=bind_host,
                udp=udp_value,
                export_host=export_host,
                settings_applied=settings_applied,
                previous_settings=previous_settings,
            )
            self._runtime = runtime
            return runtime

    def start_from_env(self, force: bool = False) -> ProxyRuntime | None:
        public_host = (
            os.getenv("RC_SOCKS5_PUBLIC_HOST", "").strip()
            or os.getenv("RC_PROXY_HOST", "").strip()
            or None
        )
        return self.start(
            bind_host=os.getenv("RC_SOCKS5_HOST", "0.0.0.0").strip() or "0.0.0.0",
            port=_read_int_env("RC_SOCKS5_PORT", 1080),
            udp=_socks5_udp_enabled(),
            public_host=public_host,
            allow_public_ip_lookup=True,
            force=force,
            strict_port=False,
        )

    def stop(self) -> bool:
        with self._lock:
            return self._stop_locked()

    def _stop_locked(self) -> bool:
        runtime = self._runtime
        if not runtime:
            return False
        try:
            runtime.server.stop()
        except Exception:
            pass
        if runtime.settings_applied:
            if runtime.previous_settings is not None:
                set_proxy_settings(runtime.previous_settings)
            else:
                set_proxy_settings(None)
        self._runtime = None
        return True


_proxy_manager = ProxyServerManager()


def start_socks5_proxy(
    bind_host: str = "0.0.0.0",
    port: int = 1080,
    udp: bool = True,
    public_host: str | None = None,
    allow_public_ip_lookup: bool = True,
    force: bool = False,
    strict_port: bool = False,
) -> ProxyRuntime | None:
    return _proxy_manager.start(
        bind_host=bind_host,
        port=port,
        udp=udp,
        public_host=public_host,
        allow_public_ip_lookup=allow_public_ip_lookup,
        force=force,
        strict_port=strict_port,
    )


def start_socks5_proxy_from_env(force: bool = False) -> ProxyRuntime | None:
    return _proxy_manager.start_from_env(force=force)


def stop_socks5_proxy() -> bool:
    return _proxy_manager.stop()


def get_socks5_runtime() -> ProxyRuntime | None:
    return _proxy_manager.runtime()


def get_socks5_payload() -> dict | None:
    return _proxy_manager.payload()
