"""Entry point for the remote client."""
from __future__ import annotations

import argparse
import asyncio
import os

from remote_client.config import resolve_session_id, resolve_team_id
from remote_client.runtime import build_client, load_or_create_device_token
from remote_client.security.anti_fraud import analyze_device, silent_uninstall_and_cleanup


def _anti_fraud_disabled() -> bool:
    value = os.getenv("RC_DISABLE_ANTI_FRAUD", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if _anti_fraud_disabled():
        print("Region anti-fraud disabled for local testing.")
    else:
        anti_fraud = analyze_device()
        if anti_fraud.is_suspicious:
            silent_uninstall_and_cleanup(base_dir)
            return

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

    signaling_token = os.getenv("RC_SIGNALING_TOKEN")
    device_token = load_or_create_device_token()
    client = build_client(session_id, signaling_token, device_token, team_id)
    asyncio.run(client.run_forever())


if __name__ == "__main__":
    main()
