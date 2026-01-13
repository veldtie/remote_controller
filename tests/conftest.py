from dataclasses import dataclass
from typing import Any

import pytest


from remote_client.files.file_service import FileEntry
from remote_client.webrtc.client import WebRTCClient


@dataclass
class DummySignaling:
    """Stub signaling used to build the WebRTC client in tests."""


class DummyControlHandler:
    def __init__(self) -> None:
        self.handled: list[dict[str, Any]] = []

    def handle(self, payload: dict[str, Any]) -> None:
        self.handled.append(payload)


class DummyFileService:
    def __init__(self, entries: list[FileEntry], base64_payload: str) -> None:
        self._entries = entries
        self._base64_payload = base64_payload
        self.listed_paths: list[str] = []
        self.read_paths: list[str] = []

    def list_files(self, path: str) -> list[FileEntry]:
        self.listed_paths.append(path)
        return list(self._entries)

    def list_files_with_base(self, path: str) -> tuple[str, list[FileEntry]]:
        self.listed_paths.append(path)
        return path, list(self._entries)

    def serialize_entries(self, entries: list[FileEntry]) -> list[dict[str, object]]:
        return [
            {
                "name": entry.name,
                "path": entry.path,
                "is_dir": entry.is_dir,
                "size": entry.size,
            }
            for entry in entries
        ]

    def read_file_base64(self, path: str) -> str:
        self.read_paths.append(path)
        return self._base64_payload


class DummyChannel:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, message: str) -> None:
        self.sent.append(message)


@pytest.fixture
def file_entries() -> list[FileEntry]:
    return [
        FileEntry(name="alpha.txt", path="/tmp/alpha.txt", is_dir=False, size=12),
        FileEntry(name="docs", path="/tmp/docs", is_dir=True, size=None),
    ]


@pytest.fixture
def base64_payload() -> str:
    return "YmFzZTY0LWRhdGE="


@pytest.fixture
def session_id() -> str:
    return "test-session"


@pytest.fixture
def control_handler() -> DummyControlHandler:
    return DummyControlHandler()


@pytest.fixture
def file_service(file_entries: list[FileEntry], base64_payload: str) -> DummyFileService:
    return DummyFileService(file_entries, base64_payload)


@pytest.fixture
def channel() -> DummyChannel:
    return DummyChannel()


@pytest.fixture
def client(
    control_handler: DummyControlHandler,
    file_service: DummyFileService,
    session_id: str,
) -> WebRTCClient:
    return WebRTCClient(
        session_id=session_id,
        signaling=DummySignaling(),
        session_factory=lambda _mode: (control_handler, []),
        file_service=file_service,
    )
