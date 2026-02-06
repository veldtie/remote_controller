"""Download and prepare IDD driver for embedding.

Run this script to download the Virtual Display Driver and prepare it
for embedding in PyInstaller builds.

Usage:
    python download_driver.py

The driver will be downloaded to ./vdd/ directory.
"""
import os
import shutil
import ssl
import sys
import urllib.request
import zipfile
from pathlib import Path

# Disable SSL verification for GitHub (some corporate networks block it)
ssl._create_default_https_context = ssl._create_unverified_context

# Driver sources (in order of preference)
DRIVER_SOURCES = [
    {
        "name": "Virtual-Display-Driver (MTT)",
        "url": "https://github.com/itsmikethetech/Virtual-Display-Driver/releases/download/24.9.17/VDD.2024.9.17.zip",
        "type": "zip",
    },
    {
        "name": "IddSampleDriver (ge9)",
        "url": "https://github.com/ge9/IddSampleDriver/releases/download/0.0.1.3/IddSampleDriver.zip",
        "type": "zip",
    },
    {
        "name": "Virtual-Display-Driver (alternative)",
        "url": "https://github.com/VirtualDisplayDriver/Virtual-Display-Driver/releases/download/24.5.12.1/VDD.2024.5.12.1.zip",
        "type": "zip",
    },
    {
        "name": "Parsec-VDD",
        "url": "https://builds.parsec.app/vdd/parsec-vdd-0.41.0.0.exe",
        "type": "exe",
        "note": "Run this exe to install Parsec VDD (signed driver)",
    },
]


def download_file(url: str, dest: Path) -> bool:
    """Download file from URL."""
    print(f"Downloading from {url}...")
    try:
        # Add headers to avoid 403 errors
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=60) as response:
            with open(dest, 'wb') as f:
                f.write(response.read())
        return True
    except Exception as e:
        print(f"  Failed: {e}")
        return False


def extract_zip(zip_path: Path, dest_dir: Path) -> bool:
    """Extract ZIP file."""
    print(f"Extracting to {dest_dir}...")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(dest_dir)
        return True
    except Exception as e:
        print(f"  Failed: {e}")
        return False


def find_inf_file(search_dir: Path) -> Path | None:
    """Find .inf file in directory."""
    inf_files = list(search_dir.rglob("*.inf"))
    return inf_files[0] if inf_files else None


def prepare_driver_package(driver_dir: Path) -> bool:
    """Prepare driver package for embedding."""
    # Find inf file
    inf = find_inf_file(driver_dir)
    if not inf:
        print("  No .inf file found!")
        return False
    
    print(f"  Found driver: {inf.name}")
    
    # Check for required files
    sys_files = list(driver_dir.rglob("*.sys"))
    cat_files = list(driver_dir.rglob("*.cat"))
    
    print(f"  .sys files: {len(sys_files)}")
    print(f"  .cat files: {len(cat_files)}")
    
    if not sys_files:
        print("  WARNING: No .sys driver file found!")
        return False
    
    # Move all files to flat structure
    final_dir = driver_dir / "package"
    final_dir.mkdir(exist_ok=True)
    
    for f in [inf] + sys_files + cat_files:
        dest = final_dir / f.name
        if f != dest:
            shutil.copy2(f, dest)
    
    print(f"  Package ready in: {final_dir}")
    return True


def main():
    script_dir = Path(__file__).parent
    vdd_dir = script_dir / "vdd"
    
    # Clean existing
    if vdd_dir.exists():
        print(f"Removing existing {vdd_dir}...")
        shutil.rmtree(vdd_dir)
    
    vdd_dir.mkdir(parents=True, exist_ok=True)
    
    print("\n" + "="*60)
    print("       Virtual Display Driver Downloader")
    print("="*60 + "\n")
    
    for source in DRIVER_SOURCES:
        print(f"\n>>> Trying: {source['name']}")
        
        if source.get("type") == "exe":
            # For exe installers, just download and notify
            exe_path = vdd_dir / Path(source["url"]).name
            if download_file(source["url"], exe_path):
                print(f"\n✓ Downloaded installer: {exe_path.name}")
                if source.get("note"):
                    print(f"  NOTE: {source['note']}")
                print("\n=== PARSEC VDD DOWNLOADED ===")
                print(f"\nRun this to install: {exe_path}")
                print("Parsec VDD is SIGNED by Microsoft - no test mode needed!")
                return 0
            continue
        
        # ZIP file handling
        zip_path = vdd_dir / "driver.zip"
        
        if not download_file(source["url"], zip_path):
            continue
            
        extract_dir = vdd_dir / "extracted"
        extract_dir.mkdir(exist_ok=True)
        
        if not extract_zip(zip_path, extract_dir):
            continue
        
        # Find driver files
        inf_files = list(extract_dir.rglob("*.inf"))
        sys_files = list(extract_dir.rglob("*.sys"))
        cat_files = list(extract_dir.rglob("*.cat"))
        dll_files = list(extract_dir.rglob("*.dll"))
        
        print(f"  Found: {len(inf_files)} .inf, {len(sys_files)} .sys, {len(cat_files)} .cat")
        
        if not inf_files:
            print("  ERROR: No .inf file found")
            shutil.rmtree(extract_dir)
            zip_path.unlink(missing_ok=True)
            continue
        
        if not sys_files:
            print("  WARNING: No .sys file - driver may be incomplete")
            # Continue anyway, some drivers work differently
        
        # Copy all driver files to vdd directory
        for f in inf_files + sys_files + cat_files + dll_files:
            dest = vdd_dir / f.name
            if not dest.exists():
                shutil.copy2(f, dest)
                print(f"  + {f.name}")
        
        # Also copy any exe control utilities
        for exe in extract_dir.rglob("*.exe"):
            if "uninstall" not in exe.name.lower():
                dest = vdd_dir / exe.name
                if not dest.exists():
                    shutil.copy2(exe, dest)
                    print(f"  + {exe.name}")
        
        # Clean up
        shutil.rmtree(extract_dir)
        zip_path.unlink(missing_ok=True)
        
        print(f"\n{'='*60}")
        print(f"  SUCCESS: Driver ready in {vdd_dir}")
        print(f"{'='*60}")
        print("\nFiles:")
        for f in sorted(vdd_dir.iterdir()):
            size = f.stat().st_size
            print(f"  {f.name:40} ({size:,} bytes)")
        
        print("\n" + "="*60)
        print("  NEXT STEPS:")
        print("="*60)
        print("\n1. Build exe:")
        print("   pyinstaller RemoteControllerClient.spec")
        print("\n2. On client machine (for unsigned drivers):")
        print("   bcdedit /set testsigning on")
        print("   (reboot required)")
        print("\n3. Run exe as Administrator")
        return 0
    
    print("\n" + "="*60)
    print("  FAILED: Could not download any driver")
    print("="*60)
    print("\nManual options:")
    print("1. Download Parsec VDD: https://parsec.app/downloads")
    print("2. Download from: https://github.com/itsmikethetech/Virtual-Display-Driver/releases")
    print("3. Place driver files (.inf, .sys, .cat) in: " + str(vdd_dir))
    return 1


if __name__ == "__main__":
    sys.exit(main())
