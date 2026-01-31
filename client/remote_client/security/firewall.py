from __future__ import annotations

import os
import subprocess
import sys

RULE_PREFIX = "RemDesk Client"


def _hidden_subprocess_kwargs() -> dict[str, object]:
    if os.name != "nt":
        return {}
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    return {"startupinfo": startup, "creationflags": subprocess.CREATE_NO_WINDOW}


def _program_path() -> str | None:
    if not sys.executable:
        return None
    return os.path.abspath(sys.executable)


def _run_netsh(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["netsh", *args],
        capture_output=True,
        text=True,
        check=False,
        **_hidden_subprocess_kwargs(),
    )


def _rule_exists(name: str) -> bool:
    result = _run_netsh(["advfirewall", "firewall", "show", "rule", f"name={name}"])
    if result.returncode != 0:
        return False
    output = (result.stdout or "") + (result.stderr or "")
    return "No rules match" not in output


def _add_rule(name: str, direction: str, program: str) -> None:
    _run_netsh(
        [
            "advfirewall",
            "firewall",
            "add",
            "rule",
            f"name={name}",
            f"dir={direction}",
            "action=allow",
            f"program={program}",
            "profile=any",
            "enable=yes",
        ]
    )


def ensure_firewall_rules() -> None:
    if os.name != "nt":
        return
    program = _program_path()
    if not program:
        return
    for direction, name in (("in", f"{RULE_PREFIX} (In)"), ("out", f"{RULE_PREFIX} (Out)")):
        if _rule_exists(name):
            continue
        _add_rule(name, direction, program)
