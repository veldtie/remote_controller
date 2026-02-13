"""
Password Extractor module for Chromium-based browsers.

Extracts and decrypts saved passwords from:
- Google Chrome
- Microsoft Edge
- Brave Browser
- Opera / Opera GX
- Vivaldi
- Dolphin Anty
- Other Chromium-based browsers

Supports:
- Standard DPAPI encryption (Chrome < 127)
- App-Bound Encryption v20 (Chrome 127+)
"""
from __future__ import annotations

from .extractor import (
    PasswordExtractor,
    ExtractedPassword,
    PasswordDecryptionError,
    extract_passwords,
    extract_all_browser_passwords,
    get_password_decryption_status,
    BROWSER_PASSWORD_CONFIG,
)

__all__ = [
    "PasswordExtractor",
    "ExtractedPassword",
    "PasswordDecryptionError",
    "extract_passwords",
    "extract_all_browser_passwords",
    "get_password_decryption_status",
    "BROWSER_PASSWORD_CONFIG",
]
