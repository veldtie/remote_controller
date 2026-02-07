class CookieExportError(RuntimeError):
    """Base exception for cookie export operations."""
    
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
    
    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": str(self),
        }


class AppBoundEncryptionError(CookieExportError):
    """Exception for App-Bound Encryption specific failures."""
    
    def __init__(self, message: str, method: str | None = None) -> None:
        super().__init__("abe_failed", message)
        self.method = method
    
    def to_dict(self) -> dict:
        result = super().to_dict()
        if self.method:
            result["method"] = self.method
        return result


class DecryptionError(CookieExportError):
    """Exception for general decryption failures."""
    
    def __init__(self, message: str, version: str | None = None) -> None:
        super().__init__("decryption_failed", message)
        self.version = version
    
    def to_dict(self) -> dict:
        result = super().to_dict()
        if self.version:
            result["version"] = self.version
        return result


# Error codes for client use
ERROR_CODES = {
    "unsupported": "Platform not supported (Windows only)",
    "missing_dependency": "Required dependency not installed",
    "cookies_not_found": "Cookies database not found",
    "cookies_empty": "No cookies extracted",
    "unsupported_browser": "Browser not supported",
    "export_failed": "Cookie export failed",
    "abe_failed": "App-Bound Encryption decryption failed",
    "decryption_failed": "Cookie value decryption failed",
}
