"""Backward-compatible launcher entry point.

The canonical script entry point is ``operator_desktop.app``.
This module remains as a thin compatibility wrapper.
"""
from __future__ import annotations

if __package__:
    from .app import main
else:
    from app import main  # type: ignore


if __name__ == "__main__":
    raise SystemExit(main())
