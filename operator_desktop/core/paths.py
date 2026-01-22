import os
from pathlib import Path


def resolve_settings_path() -> Path:
    base = os.getenv("LOCALAPPDATA")
    if base:
        path = Path(base) / "RemoteControllerOperator" / "settings.json"
    else:
        path = Path(__file__).resolve().parent / "data" / "settings.json"
    return path
