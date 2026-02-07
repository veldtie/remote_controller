from .errors import CookieExportError
from .exporter import CookieExporter

# App-Bound Encryption support (Chrome 127+)
try:
    from .app_bound_encryption import (
        AppBoundDecryptor,
        AppBoundDecryptionError,
        check_abe_support,
        is_abe_encrypted_key,
        is_abe_encrypted_value,
    )
    ABE_AVAILABLE = True
except ImportError:
    ABE_AVAILABLE = False
    AppBoundDecryptor = None
    AppBoundDecryptionError = None
    check_abe_support = None
    is_abe_encrypted_key = None
    is_abe_encrypted_value = None

__all__ = [
    "CookieExportError",
    "CookieExporter",
    "ABE_AVAILABLE",
    "AppBoundDecryptor",
    "AppBoundDecryptionError",
    "check_abe_support",
    "is_abe_encrypted_key",
    "is_abe_encrypted_value",
]
