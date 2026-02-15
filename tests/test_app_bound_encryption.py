"""Tests for App-Bound Encryption module."""
import base64
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add client directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "client"))

from remote_client.cookie_extractor.app_bound_encryption import (
    ABE_PREFIX,
    V20_PREFIX,
    AES_GCM_NONCE_LENGTH,
    AppBoundDecryptor,
    AppBoundDecryptionError,
    check_abe_support,
    decrypt_v20_value,
    is_abe_encrypted_key,
    is_abe_encrypted_value,
    load_abe_key_from_local_state,
)


class TestABEDetection:
    """Tests for ABE detection functions."""
    
    def test_is_abe_encrypted_key_with_appb_prefix(self):
        """Keys starting with APPB should be detected as ABE."""
        assert is_abe_encrypted_key(b"APPBsomedata")
        assert is_abe_encrypted_key(b"APPB" + bytes(100))
    
    def test_is_abe_encrypted_key_without_appb_prefix(self):
        """Keys without APPB prefix should not be detected as ABE."""
        assert not is_abe_encrypted_key(b"DPAPIsomedata")
        assert not is_abe_encrypted_key(b"somedata")
        assert not is_abe_encrypted_key(b"")
    
    def test_is_abe_encrypted_value_with_v20_prefix(self):
        """Values starting with v20 should be detected as ABE."""
        assert is_abe_encrypted_value(b"v20somedata")
        assert is_abe_encrypted_value(b"v20" + bytes(100))
    
    def test_is_abe_encrypted_value_without_v20_prefix(self):
        """Values without v20 prefix should not be detected as ABE."""
        assert not is_abe_encrypted_value(b"v10somedata")
        assert not is_abe_encrypted_value(b"v11somedata")
        assert not is_abe_encrypted_value(b"v12somedata")
        assert not is_abe_encrypted_value(b"")


class TestCheckABESupport:
    """Tests for ABE support checking."""
    
    def test_check_abe_support_returns_dict(self):
        """check_abe_support should return a dictionary with expected keys."""
        result = check_abe_support()
        
        assert isinstance(result, dict)
        assert "windows" in result
        assert "chrome_installed" in result
        assert "elevation_service" in result
        assert "dpapi_available" in result
    
    def test_check_abe_support_non_windows(self):
        """On non-Windows, most features should be unavailable."""
        result = check_abe_support()
        
        if os.name != "nt":
            assert result["windows"] is False
            assert result["dpapi_available"] is False


class TestAppBoundDecryptor:
    """Tests for AppBoundDecryptor class."""
    
    def test_decryptor_without_local_state_path(self):
        """Decryptor without local_state_path should not be available."""
        decryptor = AppBoundDecryptor(None)
        
        assert not decryptor.is_available
    
    def test_decryptor_with_nonexistent_path(self):
        """Decryptor with nonexistent path should not be available."""
        decryptor = AppBoundDecryptor(Path("/nonexistent/path"))
        
        assert not decryptor.is_available
    
    def test_can_decrypt_value_when_not_available(self):
        """can_decrypt_value should return False when decryptor is not available."""
        decryptor = AppBoundDecryptor(None)
        
        assert not decryptor.can_decrypt_value(b"v20test")
    
    def test_decrypt_value_raises_when_not_available(self):
        """decrypt_value should raise when decryptor is not available."""
        decryptor = AppBoundDecryptor(None)
        
        with pytest.raises(AppBoundDecryptionError):
            decryptor.decrypt_value(b"v20test")


class TestDecryptV20Value:
    """Tests for v20 value decryption."""
    
    def test_decrypt_v20_requires_v20_prefix(self):
        """decrypt_v20_value should raise for non-v20 values."""
        with pytest.raises(AppBoundDecryptionError):
            decrypt_v20_value(b"v10somedata", b"0" * 32)
    
    def test_decrypt_v20_with_valid_key(self):
        """decrypt_v20_value should work with valid key and ciphertext."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        
        # Create valid encrypted data
        key = os.urandom(32)
        nonce = os.urandom(AES_GCM_NONCE_LENGTH)
        plaintext = "test_cookie_value"
        
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        
        encrypted_value = V20_PREFIX + nonce + ciphertext
        
        # Decrypt and verify
        result = decrypt_v20_value(encrypted_value, key)
        assert result == plaintext
    
    def test_decrypt_v20_with_wrong_key(self):
        """decrypt_v20_value should raise with wrong key."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        
        # Create encrypted data with one key
        key1 = os.urandom(32)
        key2 = os.urandom(32)  # Different key
        nonce = os.urandom(AES_GCM_NONCE_LENGTH)
        plaintext = "test_cookie_value"
        
        aesgcm = AESGCM(key1)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        
        encrypted_value = V20_PREFIX + nonce + ciphertext
        
        # Try to decrypt with wrong key
        with pytest.raises(AppBoundDecryptionError):
            decrypt_v20_value(encrypted_value, key2)


class TestLoadABEKeyFromLocalState:
    """Tests for loading ABE key from Local State."""
    
    def test_load_key_nonexistent_file(self):
        """Should return None for nonexistent file."""
        result = load_abe_key_from_local_state(Path("/nonexistent/path"))
        assert result is None
    
    def test_load_key_invalid_json(self):
        """Should return None for invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json")
            temp_path = Path(f.name)
        
        try:
            result = load_abe_key_from_local_state(temp_path)
            assert result is None
        finally:
            temp_path.unlink()
    
    def test_load_key_missing_os_crypt(self):
        """Should return None when os_crypt key is missing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"other": "data"}, f)
            temp_path = Path(f.name)
        
        try:
            result = load_abe_key_from_local_state(temp_path)
            assert result is None
        finally:
            temp_path.unlink()
    
    def test_load_key_dpapi_format_skipped(self):
        """Should return None for DPAPI keys (not ABE)."""
        # Create a Local State with DPAPI key
        encrypted_key = b"DPAPI" + os.urandom(32)
        encrypted_key_b64 = base64.b64encode(encrypted_key).decode()
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "os_crypt": {
                    "encrypted_key": encrypted_key_b64
                }
            }, f)
            temp_path = Path(f.name)
        
        try:
            result = load_abe_key_from_local_state(temp_path)
            # Should return None because it's not ABE format
            assert result is None
        finally:
            temp_path.unlink()


class TestConstants:
    """Tests for module constants."""
    
    def test_abe_prefix(self):
        assert ABE_PREFIX == b"APPB"
    
    def test_v20_prefix(self):
        assert V20_PREFIX == b"v20"
    
    def test_aes_gcm_nonce_length(self):
        assert AES_GCM_NONCE_LENGTH == 12
