#!/usr/bin/env python3
"""
Disable Chrome App-Bound Encryption (ABE) via Windows Registry

This script disables ABE so Chrome uses the old DPAPI encryption method.
After disabling, NEW cookies will be encrypted with v10 (DPAPI) instead of v20 (ABE).

⚠️ WARNING: This reduces security! Use at your own risk.

Usage:
    python disable_abe.py --disable   # Disable ABE
    python disable_abe.py --enable    # Re-enable ABE
    python disable_abe.py --status    # Check current status

Requirements:
    - Run as Administrator
    - Windows 10/11
    - Chrome 127+
"""

import sys
import os
import subprocess
import ctypes
from typing import Optional, Tuple

# Registry paths
HKLM_CHROME_POLICIES = r"SOFTWARE\Policies\Google\Chrome"
HKCU_CHROME_POLICIES = r"SOFTWARE\Policies\Google\Chrome"

# Policy name for ABE
ABE_POLICY_NAME = "ApplicationBoundEncryptionEnabled"


def is_admin() -> bool:
    """Check if script is running with admin privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def run_as_admin():
    """Relaunch script as administrator."""
    if sys.platform != 'win32':
        print("[-] This script only works on Windows")
        sys.exit(1)
    
    script = os.path.abspath(sys.argv[0])
    params = ' '.join(sys.argv[1:])
    
    print("[*] Requesting administrator privileges...")
    
    try:
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'"{script}" {params}', None, 1
        )
        sys.exit(0)
    except Exception as e:
        print(f"[-] Failed to elevate: {e}")
        sys.exit(1)


def reg_key_exists(hive: str, path: str) -> bool:
    """Check if registry key exists."""
    try:
        result = subprocess.run(
            ["reg", "query", f"{hive}\\{path}"],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def reg_value_get(hive: str, path: str, name: str) -> Optional[int]:
    """Get registry DWORD value."""
    try:
        result = subprocess.run(
            ["reg", "query", f"{hive}\\{path}", "/v", name],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            # Parse output like: "    ApplicationBoundEncryptionEnabled    REG_DWORD    0x0"
            for line in result.stdout.split('\n'):
                if name in line and "REG_DWORD" in line:
                    parts = line.strip().split()
                    for part in parts:
                        if part.startswith("0x"):
                            return int(part, 16)
        return None
    except Exception:
        return None


def reg_value_set(hive: str, path: str, name: str, value: int) -> bool:
    """Set registry DWORD value."""
    try:
        # Create key if not exists
        subprocess.run(
            ["reg", "add", f"{hive}\\{path}", "/f"],
            capture_output=True
        )
        
        # Set value
        result = subprocess.run(
            ["reg", "add", f"{hive}\\{path}", "/v", name, "/t", "REG_DWORD", "/d", str(value), "/f"],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[-] Registry error: {e}")
        return False


def reg_value_delete(hive: str, path: str, name: str) -> bool:
    """Delete registry value."""
    try:
        result = subprocess.run(
            ["reg", "delete", f"{hive}\\{path}", "/v", name, "/f"],
            capture_output=True
        )
        return result.returncode == 0
    except Exception:
        return False


def get_abe_status() -> Tuple[bool, str]:
    """
    Get current ABE status from registry.
    Returns: (is_disabled, description)
    """
    # Check HKLM first (machine policy takes precedence)
    hklm_value = reg_value_get("HKLM", HKLM_CHROME_POLICIES, ABE_POLICY_NAME)
    hkcu_value = reg_value_get("HKCU", HKCU_CHROME_POLICIES, ABE_POLICY_NAME)
    
    if hklm_value == 0:
        return True, "DISABLED (HKLM policy)"
    elif hklm_value == 1:
        return False, "ENABLED (HKLM policy)"
    elif hkcu_value == 0:
        return True, "DISABLED (HKCU policy)"
    elif hkcu_value == 1:
        return False, "ENABLED (HKCU policy)"
    else:
        return False, "ENABLED (default - no policy set)"


def disable_abe() -> bool:
    """Disable ABE via registry policy."""
    print("[*] Disabling App-Bound Encryption...")
    
    # Set policy in HKLM (requires admin)
    if reg_value_set("HKLM", HKLM_CHROME_POLICIES, ABE_POLICY_NAME, 0):
        print("[+] Set HKLM policy: ApplicationBoundEncryptionEnabled = 0")
        return True
    
    # Fallback to HKCU
    print("[!] HKLM failed, trying HKCU...")
    if reg_value_set("HKCU", HKCU_CHROME_POLICIES, ABE_POLICY_NAME, 0):
        print("[+] Set HKCU policy: ApplicationBoundEncryptionEnabled = 0")
        return True
    
    return False


def enable_abe() -> bool:
    """Re-enable ABE (remove policy or set to 1)."""
    print("[*] Re-enabling App-Bound Encryption...")
    
    # Remove policy from both locations
    removed_hklm = reg_value_delete("HKLM", HKLM_CHROME_POLICIES, ABE_POLICY_NAME)
    removed_hkcu = reg_value_delete("HKCU", HKCU_CHROME_POLICIES, ABE_POLICY_NAME)
    
    if removed_hklm:
        print("[+] Removed HKLM policy")
    if removed_hkcu:
        print("[+] Removed HKCU policy")
    
    if not removed_hklm and not removed_hkcu:
        print("[*] No policy was set, ABE is already enabled by default")
    
    return True


def kill_chrome():
    """Kill Chrome processes."""
    print("[*] Closing Chrome...")
    try:
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], 
                      capture_output=True, timeout=10)
    except Exception:
        pass


def clear_chrome_cookies():
    """Clear Chrome cookies to force re-encryption with new method."""
    import shutil
    from pathlib import Path
    
    user_data = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
    
    cookies_paths = [
        user_data / "Default" / "Network" / "Cookies",
        user_data / "Default" / "Network" / "Cookies-journal",
        user_data / "Default" / "Cookies",  # Old location
    ]
    
    # Also check other profiles
    for item in user_data.iterdir() if user_data.exists() else []:
        if item.is_dir() and item.name.startswith("Profile"):
            cookies_paths.append(item / "Network" / "Cookies")
            cookies_paths.append(item / "Network" / "Cookies-journal")
    
    deleted = 0
    for path in cookies_paths:
        if path.exists():
            try:
                path.unlink()
                print(f"[+] Deleted: {path}")
                deleted += 1
            except Exception as e:
                print(f"[-] Failed to delete {path}: {e}")
    
    return deleted


def print_status():
    """Print current ABE status."""
    is_disabled, description = get_abe_status()
    
    print("\n" + "=" * 60)
    print("  Chrome App-Bound Encryption Status")
    print("=" * 60)
    print(f"\n  Status: {description}")
    print(f"\n  ABE is currently: {'DISABLED ✓' if is_disabled else 'ENABLED'}")
    
    if is_disabled:
        print("""
  New cookies will be encrypted with DPAPI (v10/v11/v12).
  These can be decrypted without IElevator COM.
  
  ⚠️  Existing v20 cookies are still ABE-encrypted!
      To fully switch to DPAPI, clear Chrome cookies.
""")
    else:
        print("""
  Cookies are encrypted with ABE (v20).
  Decryption requires IElevator COM or CDP method.
  
  To disable ABE, run: python disable_abe.py --disable
""")
    print("=" * 60)


def print_help():
    """Print usage help."""
    print("""
╔════════════════════════════════════════════════════════════════╗
║     Disable Chrome App-Bound Encryption (ABE)                  ║
╠════════════════════════════════════════════════════════════════╣
║                                                                 ║
║  Usage:                                                         ║
║    python disable_abe.py --status    Check current status       ║
║    python disable_abe.py --disable   Disable ABE                ║
║    python disable_abe.py --enable    Re-enable ABE              ║
║    python disable_abe.py --clear     Clear cookies after        ║
║                                                                 ║
║  ⚠️  WARNING: Disabling ABE reduces security!                   ║
║                                                                 ║
║  After disabling ABE:                                           ║
║  • NEW cookies → v10/v11/v12 (DPAPI) - easy to decrypt         ║
║  • OLD cookies → still v20 (ABE) - need CDP/IElevator          ║
║                                                                 ║
║  To fully convert to DPAPI:                                     ║
║  1. Run: python disable_abe.py --disable                        ║
║  2. Run: python disable_abe.py --clear  (deletes all cookies!)  ║
║  3. Restart Chrome and log in to sites again                    ║
║                                                                 ║
╚════════════════════════════════════════════════════════════════╝
""")


def main():
    if sys.platform != 'win32':
        print("[-] This script only works on Windows!")
        return 1
    
    if len(sys.argv) < 2:
        print_help()
        print_status()
        return 0
    
    action = sys.argv[1].lower()
    
    if action in ['--help', '-h', 'help']:
        print_help()
        return 0
    
    if action in ['--status', '-s', 'status']:
        print_status()
        return 0
    
    if action in ['--disable', '-d', 'disable']:
        if not is_admin():
            print("[!] Administrator privileges required!")
            run_as_admin()
            return 0
        
        print("""
╔════════════════════════════════════════════════════════════════╗
║  ⚠️  WARNING: You are about to DISABLE App-Bound Encryption    ║
║                                                                 ║
║  This will:                                                     ║
║  • Reduce cookie security                                       ║
║  • Allow easier cookie extraction                               ║
║  • Affect only NEW cookies (existing v20 cookies remain)       ║
║                                                                 ║
║  Registry change:                                               ║
║  HKLM\\SOFTWARE\\Policies\\Google\\Chrome                         ║
║  ApplicationBoundEncryptionEnabled = 0                          ║
╚════════════════════════════════════════════════════════════════╝
""")
        
        response = input("  Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("[-] Aborted.")
            return 1
        
        kill_chrome()
        
        if disable_abe():
            print("\n[+] ABE disabled successfully!")
            print("\n[*] IMPORTANT: Restart Chrome for changes to take effect.")
            print("[*] New cookies will use DPAPI (v10) instead of ABE (v20).")
            
            response = input("\n[?] Clear existing cookies to force DPAPI? (yes/no): ")
            if response.lower() == 'yes':
                deleted = clear_chrome_cookies()
                print(f"[+] Deleted {deleted} cookie files.")
                print("[*] Restart Chrome and log in to sites again.")
            
            print_status()
            return 0
        else:
            print("[-] Failed to disable ABE!")
            return 1
    
    if action in ['--enable', '-e', 'enable']:
        if not is_admin():
            print("[!] Administrator privileges required!")
            run_as_admin()
            return 0
        
        kill_chrome()
        
        if enable_abe():
            print("[+] ABE re-enabled (default behavior).")
            print("[*] Restart Chrome for changes to take effect.")
            print_status()
            return 0
        else:
            print("[-] Failed to enable ABE!")
            return 1
    
    if action in ['--clear', '-c', 'clear']:
        print("[!] This will DELETE all Chrome cookies!")
        response = input("    Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("[-] Aborted.")
            return 1
        
        kill_chrome()
        deleted = clear_chrome_cookies()
        print(f"[+] Deleted {deleted} cookie files.")
        print("[*] Restart Chrome and log in to sites again.")
        return 0
    
    print(f"[-] Unknown action: {action}")
    print_help()
    return 1


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
