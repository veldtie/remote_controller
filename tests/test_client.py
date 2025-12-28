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

    asyncio.run(client._handle_message(channel, payload))

    assert control_handler.handled == [payload]
    assert channel.sent == []


def test_handle_list_files_sends_serialized_entries(
    client, file_service, file_entries, channel
):
    payload = {"action": "list_files", "path": "/tmp"}

    asyncio.run(client._handle_message(channel, payload))

    assert file_service.listed_paths == ["/tmp"]
    assert len(channel.sent) == 1
    message = json.loads(channel.sent[0])
    assert message["files"] == file_service.serialize_entries(file_entries)


def test_handle_download_sends_payload(client, file_service, base64_payload, channel):
    payload = {"action": "download", "path": "/tmp/report.txt"}

    asyncio.run(client._handle_message(channel, payload))

    assert file_service.read_paths == ["/tmp/report.txt"]
    assert channel.sent == [base64_payload]


def test_integration_download_reads_and_transfers_file(tmp_path, control_handler):
    source_file = tmp_path / "report.bin"
    source_bytes = b"binary-payload-\x00\x01"
    source_file.write_bytes(source_bytes)

    file_service = FileService()
    client = WebRTCClient(
        signaling=None,
        control_handler=control_handler,
        file_service=file_service,
        media_tracks=[],
    )
    channel = CapturingChannel()

    payload = {"action": "download", "path": str(source_file)}
    asyncio.run(client._handle_message(channel, payload))

    assert channel.sent == [base64.b64encode(source_bytes).decode()]

    received_file = tmp_path / "received.bin"
    received_bytes = base64.b64decode(channel.sent[0])
    received_file.write_bytes(received_bytes)
    assert received_file.read_bytes() == source_bytes
