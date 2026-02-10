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

# Opera App-Bound Encryption support
try:
    from .app_bound_encryption_opera import (
        OperaAppBoundDecryptor,
        OperaAppBoundDecryptionError,
        check_opera_abe_support,
    )
    OPERA_ABE_AVAILABLE = True
except ImportError:
    OPERA_ABE_AVAILABLE = False
    OperaAppBoundDecryptor = None
    OperaAppBoundDecryptionError = None
    check_opera_abe_support = None

# Edge App-Bound Encryption support
try:
    from .app_bound_encryption_edge import (
        EdgeAppBoundDecryptor,
        EdgeAppBoundDecryptionError,
        check_edge_abe_support,
    )
    EDGE_ABE_AVAILABLE = True
except ImportError:
    EDGE_ABE_AVAILABLE = False
    EdgeAppBoundDecryptor = None
    EdgeAppBoundDecryptionError = None
    check_edge_abe_support = None

# Brave App-Bound Encryption support
try:
    from .app_bound_encryption_brave import (
        BraveAppBoundDecryptor,
        BraveAppBoundDecryptionError,
        check_brave_abe_support,
    )
    BRAVE_ABE_AVAILABLE = True
except ImportError:
    BRAVE_ABE_AVAILABLE = False
    BraveAppBoundDecryptor = None
    BraveAppBoundDecryptionError = None
    check_brave_abe_support = None

# Dolphin Anty App-Bound Encryption support
try:
    from .app_bound_encryption_dolphin import (
        DolphinAppBoundDecryptor,
        DolphinAppBoundDecryptionError,
        check_dolphin_abe_support,
    )
    DOLPHIN_ABE_AVAILABLE = True
except ImportError:
    DOLPHIN_ABE_AVAILABLE = False
    DolphinAppBoundDecryptor = None
    DolphinAppBoundDecryptionError = None
    check_dolphin_abe_support = None

# Firefox support (no ABE - uses NSS)
try:
    from .firefox import (
        extract_firefox,
        extract_all_firefox_browsers,
        check_firefox_support,
        check_all_firefox_support,
        get_firefox_cookie_paths,
        get_all_firefox_cookie_paths,
        FIREFOX_BROWSERS,
    )
    FIREFOX_AVAILABLE = True
except ImportError:
    FIREFOX_AVAILABLE = False
    extract_firefox = None
    extract_all_firefox_browsers = None
    check_firefox_support = None
    check_all_firefox_support = None
    get_firefox_cookie_paths = None
    get_all_firefox_cookie_paths = None
    FIREFOX_BROWSERS = None

__all__ = [
    "CookieExportError",
    "CookieExporter",
    # Chrome ABE
    "ABE_AVAILABLE",
    "AppBoundDecryptor",
    "AppBoundDecryptionError",
    "check_abe_support",
    "is_abe_encrypted_key",
    "is_abe_encrypted_value",
    # Opera ABE
    "OPERA_ABE_AVAILABLE",
    "OperaAppBoundDecryptor",
    "OperaAppBoundDecryptionError",
    "check_opera_abe_support",
    # Edge ABE
    "EDGE_ABE_AVAILABLE",
    "EdgeAppBoundDecryptor",
    "EdgeAppBoundDecryptionError",
    "check_edge_abe_support",
    # Brave ABE
    "BRAVE_ABE_AVAILABLE",
    "BraveAppBoundDecryptor",
    "BraveAppBoundDecryptionError",
    "check_brave_abe_support",
    # Dolphin ABE
    "DOLPHIN_ABE_AVAILABLE",
    "DolphinAppBoundDecryptor",
    "DolphinAppBoundDecryptionError",
    "check_dolphin_abe_support",
    # Firefox (no ABE)
    "FIREFOX_AVAILABLE",
    "extract_firefox",
    "extract_all_firefox_browsers",
    "check_firefox_support",
    "check_all_firefox_support",
    "get_firefox_cookie_paths",
    "get_all_firefox_cookie_paths",
    "FIREFOX_BROWSERS",
]
