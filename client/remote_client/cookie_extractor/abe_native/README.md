# ABE Native Module

Native C++ implementation for Chrome 127+ App-Bound Encryption (ABE) decryption.

## Overview

This module provides high-performance native implementations for:

1. **IElevator COM Interface** - Decrypts ABE keys via browser elevation services
2. **AES-GCM Decryption** - Decrypts v20-encrypted cookie/password values

Based on [Alexander 'xaitax' Hagenah's research](https://github.com/xaitax/Chrome-App-Bound-Encryption-Decryption).

## Requirements

### Build Requirements
- Windows 10/11 (64-bit)
- Visual Studio 2019+ with C++ workload
- CMake >= 3.15
- Python >= 3.8 with development headers
- pybind11 >= 2.11.0

### Runtime Requirements
- Windows 10/11
- Browser with elevation service (Chrome 127+, Edge, Brave, etc.)

## Installation

### From source

```bash
pip install pybind11 cmake
pip install .
```

### Build wheel

```bash
pip wheel . --no-deps
```

## Usage

```python
import abe_native

# Check platform
if not abe_native.is_windows():
    print("ABE native requires Windows")
    exit(1)

# Decrypt ABE key using IElevator COM
elevator = abe_native.Elevator()

# Auto-detect browser
result = elevator.decrypt_key_auto(encrypted_key)
if result['success']:
    abe_key = result['data']
else:
    print(f"Error: {result['error']}")

# Or specify browser
result = elevator.decrypt_key(encrypted_key, abe_native.browsers.CHROME)

# Decrypt v20 encrypted value
plaintext = abe_native.decrypt_aes_gcm(abe_key, encrypted_value)
if plaintext is not None:
    value = plaintext.decode('utf-8')
```

## Supported Browsers

- Chrome (Stable, Beta, Dev, Canary)
- Edge (Stable, Beta, Dev, Canary)  
- Brave (Stable, Beta, Nightly)
- Avast Secure Browser
- Opera (via Chrome mechanism)
- Vivaldi (via Chrome mechanism)

## API Reference

### Functions

- `is_windows()` - Returns True if running on Windows
- `is_abe_encrypted_key(data)` - Check if bytes have APPB prefix
- `is_abe_encrypted_value(data)` - Check if bytes have v20 prefix
- `decrypt_aes_gcm(key, encrypted_data)` - Decrypt v20 format data
- `decrypt_aes_gcm_raw(key, iv, ciphertext, tag)` - Decrypt raw AES-GCM

### Classes

- `Elevator` - IElevator COM interface wrapper
  - `decrypt_key(encrypted_key, browser_type)` - Decrypt with specific browser
  - `decrypt_key_auto(encrypted_key)` - Auto-detect browser and decrypt

### Constants (abe_native.browsers)

- `CHROME`, `CHROME_BETA`, `CHROME_DEV`, `CHROME_CANARY`
- `EDGE`, `EDGE_BETA`, `EDGE_DEV`, `EDGE_CANARY`
- `BRAVE`, `BRAVE_BETA`, `BRAVE_NIGHTLY`
- `AVAST`, `OPERA`, `VIVALDI`

## License

MIT License - Based on xaitax's Chrome ABE research.
