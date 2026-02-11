"""Password Extractor module for Chromium-based browsers.

Extracts and decrypts saved passwords from Chrome, Edge, Brave, Opera, etc.
Supports App-Bound Encryption (ABE) introduced in Chrome 127+.

For Chrome 127+, passwords are encrypted with ABE which requires special handling.
Unlike cookies, Chrome does not expose decrypted passwords via CDP.
"""
from .extractor import (
    PasswordExtractor,
    extract_passwords,
    extract_all_browser_passwords,
    get_password_decryption_status,
)

__all__ = [
    "PasswordExtractor",
    "extract_passwords",
    "extract_all_browser_passwords",
    "get_password_decryption_status",
]
