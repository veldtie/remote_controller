import asyncio
import json

from remote_client.files.file_service import FileService
from remote_client.main import build_client


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


def test_build_client_uses_env_and_components(monkeypatch):
    dummy_signaling = object()

    class DummyInputController:
        pass

    class DummyControlHandler:
        def __init__(self, controller):
            self.controller = controller

    class DummyScreenTrack:
        pass

    class DummyAudioTrack:
        pass

    def fake_create_signaling(host, port):
        assert host == "test-host"
        assert port == 1234
        return dummy_signaling

    monkeypatch.setenv("RC_SIGNALING_HOST", "test-host")
    monkeypatch.setenv("RC_SIGNALING_PORT", "1234")
    monkeypatch.setattr("remote_client.main.InputController", DummyInputController)
    monkeypatch.setattr("remote_client.main.ControlHandler", DummyControlHandler)
    monkeypatch.setattr("remote_client.main.ScreenTrack", DummyScreenTrack)
    monkeypatch.setattr("remote_client.main.AudioTrack", DummyAudioTrack)
    monkeypatch.setattr("remote_client.main.create_signaling", fake_create_signaling)

    client = build_client()

    assert client._signaling is dummy_signaling
    assert isinstance(client._control_handler, DummyControlHandler)
    assert isinstance(client._control_handler.controller, DummyInputController)
    assert isinstance(client._file_service, FileService)
    assert len(client._media_tracks) == 2
    assert isinstance(client._media_tracks[0], DummyScreenTrack)
    assert isinstance(client._media_tracks[1], DummyAudioTrack)
