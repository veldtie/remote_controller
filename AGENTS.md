# Remote Controller - Agent Notes

## Project Structure

- `client/` - Python client that runs on remote Windows machines
  - `remote_client/runtime.py` - Session resource builder
  - `remote_client/webrtc/client.py` - WebRTC client
  - `remote_client/windows/hvnc_track.py` - HVNC (Hidden VNC) video tracks
- `operator/` - Web UI for operators
  - `js/app_connection.js` - WebRTC connection handling
  - `js/app_core.js` - State and DOM management
- `server/` - Signaling server

## Key Features

### Dual-Stream HVNC Mode

Added support for simultaneous viewing of main desktop and HVNC hidden desktop:

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

## Build Commands

```bash
# Install dependencies
pip install -r client/requirements-client.txt

# Run tests
pytest tests/

# Build client for Windows (on Windows)
cd client && build_windows.bat
```

## Notes for Future Development

- Track IDs are used to distinguish streams: `main_desktop` vs `hvnc_desktop`
- Second video transceiver is only added when session mode is `hvnc`
- Dual-stream controls appear automatically when two video tracks are received
