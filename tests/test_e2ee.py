import json

import pytest

from remote_client.security.e2ee import E2EEContext, E2EEError


def test_e2ee_roundtrip() -> None:
    context = E2EEContext.from_passphrase("shared-passphrase", "session-123")
    plaintext = json.dumps({"action": "control", "type": "mouse_move", "x": 1, "y": 2})

    envelope = context.encrypt_text(plaintext)
    parsed = json.loads(envelope)

    assert E2EEContext.is_envelope(parsed)
    assert context.decrypt_envelope(parsed) == plaintext


def test_e2ee_rejects_invalid_payload() -> None:
    context = E2EEContext.from_passphrase("shared-passphrase", "session-123")
    with pytest.raises(E2EEError):
        context.decrypt_envelope({"e2ee": 1, "nonce": "bad", "ciphertext": "bad"})
