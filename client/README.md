# Client

Windows agent that captures desktop/audio, exposes HVNC, and connects to the signaling server via WebRTC.

**Install**
1. Create and activate a virtual environment.
2. `pip install -r requirements-client.txt`

**Run**
- `python client.py`

**Build**
- `build_windows.bat` (interactive)
- `build_windows_silent.bat` (silent)

**Key environment variables**
- `RC_SIGNALING_HOST` and `RC_SIGNALING_PORT`, or `RC_SIGNALING_URL`
- `RC_SIGNALING_TOKEN` or `RC_API_TOKEN`
- `RC_SESSION_ID` or `RC_SIGNALING_SESSION`
- `RC_HVNC_DUAL_STREAM=1` (dual stream) or `RC_HVNC_DUAL_STREAM=0` (single stream)
