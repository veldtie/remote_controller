import os
import sys
import urllib.request


def _load_token() -> str:
    token = os.getenv("RC_SIGNALING_TOKEN", "").strip()
    token_path = os.getenv("RC_SIGNALING_TOKEN_FILE", "/data/signaling_token")
    if token:
        return token
    if token_path:
        try:
            with open(token_path, "r", encoding="utf-8") as handle:
                stored = handle.read().strip()
                if stored:
                    return stored
        except OSError:
            pass
    return token


def main() -> int:
    token = _load_token()
    headers = {}
    if token:
        headers["x-rc-token"] = token
    request = urllib.request.Request("http://127.0.0.1:8000/ice-config", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            if response.status >= 400:
                return 1
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
