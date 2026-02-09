"""Activity data sender to server with local caching."""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .tracker import ActivityEntry, ActivityTracker

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """Configuration for local cache."""
    cache_dir: Path = field(default_factory=lambda: Path.home() / ".remote_controller" / "activity_cache")
    max_cache_files: int = 100
    max_entries_per_file: int = 500


class ActivitySender:
    """Send activity data to server with local caching support."""

    def __init__(
        self,
        session_id: str,
        server_url: str | None = None,
        token: str | None = None,
        send_interval: float = 0.5,  # Send immediately but with minimal batching
        cache_config: CacheConfig | None = None,
    ):
        """Initialize activity sender.
        
        Args:
            session_id: Client session ID
            server_url: Server URL for API
            token: API authentication token
            send_interval: Interval between send attempts (seconds)
            cache_config: Local cache configuration
        """
        self._session_id = session_id
        self._server_url = self._normalize_url(server_url)
        self._token = token
        self._send_interval = send_interval
        self._cache_config = cache_config or CacheConfig()
        
        self._tracker: ActivityTracker | None = None
        self._send_queue: queue.Queue[ActivityEntry] = queue.Queue()
        self._send_thread: threading.Thread | None = None
        self._running = False
        self._server_available = True
        self._cache_lock = threading.Lock()
        
        # Ensure cache directory exists
        self._cache_config.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _normalize_url(url: str | None) -> str:
        """Normalize server URL."""
        if not url:
            return ""
        url = url.strip()
        if not url:
            return ""
        # Convert websocket URL to HTTP
        if url.startswith("ws://"):
            url = "http://" + url[5:]
        elif url.startswith("wss://"):
            url = "https://" + url[6:]
        elif not url.startswith("http://") and not url.startswith("https://"):
            url = "http://" + url
        return url.rstrip("/")

    def start(self, tracker: ActivityTracker | None = None) -> None:
        """Start sender with optional existing tracker."""
        if self._running:
            return

        self._running = True
        
        # Use provided tracker or create new one
        if tracker:
            self._tracker = tracker
        else:
            self._tracker = ActivityTracker(on_activity=self._on_activity)
            self._tracker.start()

        # Start send thread
        self._send_thread = threading.Thread(target=self._send_loop, daemon=True)
        self._send_thread.start()

        # Send cached data on startup
        self._send_cached_data()
        
        logger.info("Activity sender started for session %s", self._session_id)

    def stop(self) -> None:
        """Stop sender and flush remaining data."""
        self._running = False
        if self._tracker:
            self._tracker.stop()
        self._flush_to_cache()
        logger.info("Activity sender stopped")

    def _on_activity(self, entry: ActivityEntry) -> None:
        """Called when new activity is recorded."""
        self._send_queue.put(entry)

    def _send_loop(self) -> None:
        """Main send loop."""
        batch: list[ActivityEntry] = []
        
        while self._running:
            try:
                # Collect entries from queue
                try:
                    while True:
                        entry = self._send_queue.get_nowait()
                        batch.append(entry)
                        if len(batch) >= 10:  # Batch size limit
                            break
                except queue.Empty:
                    pass

                # Also collect from tracker directly
                if self._tracker:
                    entries = self._tracker.get_pending_entries()
                    batch.extend(entries)

                # Send batch if not empty
                if batch:
                    if self._server_available and self._server_url:
                        success = self._send_to_server(batch)
                        if success:
                            batch = []
                        else:
                            self._server_available = False
                            self._cache_entries(batch)
                            batch = []
                    else:
                        self._cache_entries(batch)
                        batch = []
                        # Periodically check if server is back
                        if not self._server_available:
                            self._check_server_availability()

                time.sleep(self._send_interval)

            except Exception as e:
                logger.debug("Send loop error: %s", e)
                time.sleep(1.0)

    def _send_to_server(self, entries: list[ActivityEntry]) -> bool:
        """Send entries to server API."""
        if not self._server_url:
            return False

        url = f"{self._server_url}/api/activity-logs"
        payload = {
            "session_id": self._session_id,
            "entries": [e.to_dict() for e in entries],
        }

        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["x-rc-token"] = self._token

        try:
            data = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status == 200:
                    logger.debug("Sent %d activity entries", len(entries))
                    return True
        except urllib.error.URLError as e:
            logger.debug("Server unavailable: %s", e)
        except Exception as e:
            logger.debug("Send error: %s", e)

        return False

    def _check_server_availability(self) -> None:
        """Check if server is available and send cached data."""
        if not self._server_url:
            return

        try:
            url = f"{self._server_url}/api/health"
            headers = {}
            if self._token:
                headers["x-rc-token"] = self._token

            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=3) as response:
                if response.status == 200:
                    self._server_available = True
                    logger.info("Server connection restored")
                    self._send_cached_data()
        except Exception:
            pass

    def _cache_entries(self, entries: list[ActivityEntry]) -> None:
        """Cache entries to local file."""
        if not entries:
            return

        with self._cache_lock:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
            cache_file = self._cache_config.cache_dir / f"activity_{timestamp}.json"
            
            try:
                data = {
                    "session_id": self._session_id,
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                    "entries": [e.to_dict() for e in entries],
                }
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                logger.debug("Cached %d entries to %s", len(entries), cache_file.name)
            except Exception as e:
                logger.debug("Cache write error: %s", e)

            # Cleanup old cache files
            self._cleanup_cache()

    def _cleanup_cache(self) -> None:
        """Remove old cache files if exceeding limit."""
        try:
            cache_files = sorted(
                self._cache_config.cache_dir.glob("activity_*.json"),
                key=lambda p: p.stat().st_mtime,
            )
            while len(cache_files) > self._cache_config.max_cache_files:
                oldest = cache_files.pop(0)
                oldest.unlink()
                logger.debug("Removed old cache file: %s", oldest.name)
        except Exception as e:
            logger.debug("Cache cleanup error: %s", e)

    def _send_cached_data(self) -> None:
        """Send all cached data to server."""
        if not self._server_url:
            return

        with self._cache_lock:
            cache_files = sorted(
                self._cache_config.cache_dir.glob("activity_*.json"),
                key=lambda p: p.stat().st_mtime,
            )

            for cache_file in cache_files:
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    entries_data = data.get("entries", [])
                    if not entries_data:
                        cache_file.unlink()
                        continue

                    # Convert back to ActivityEntry objects
                    entries = [
                        ActivityEntry(
                            timestamp=e.get("timestamp", ""),
                            application=e.get("application", "Unknown"),
                            window_title=e.get("window_title", "Unknown"),
                            input_text=e.get("input_text", ""),
                            entry_type=e.get("entry_type", "keystroke"),
                        )
                        for e in entries_data
                    ]

                    if self._send_to_server(entries):
                        cache_file.unlink()
                        logger.debug("Sent cached file: %s", cache_file.name)
                    else:
                        break  # Server unavailable, stop sending

                except Exception as e:
                    logger.debug("Cache send error: %s", e)

    def _flush_to_cache(self) -> None:
        """Flush remaining queue entries to cache."""
        entries = []
        while True:
            try:
                entry = self._send_queue.get_nowait()
                entries.append(entry)
            except queue.Empty:
                break

        if self._tracker:
            entries.extend(self._tracker.get_pending_entries())

        if entries:
            self._cache_entries(entries)


def start_activity_tracking(
    session_id: str,
    server_url: str | None = None,
    token: str | None = None,
) -> ActivitySender | None:
    """Convenience function to start activity tracking.
    
    Args:
        session_id: Client session ID
        server_url: Server URL
        token: API token
        
    Returns:
        ActivitySender instance or None if disabled/failed
    """
    # Check if activity tracking is enabled
    enabled = os.getenv("RC_ACTIVITY_TRACKER", "0").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        logger.info("Activity tracking disabled")
        return None

    try:
        tracker = ActivityTracker()
        sender = ActivitySender(
            session_id=session_id,
            server_url=server_url,
            token=token,
        )
        sender.start(tracker)
        tracker.start()
        return sender
    except Exception as e:
        logger.warning("Failed to start activity tracking: %s", e)
        return None
