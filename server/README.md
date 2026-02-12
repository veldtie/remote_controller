# Signaling Server

FastAPI signaling server with WebSocket endpoints and Postgres-backed state.

**Install**
1. Create and activate a virtual environment.
2. `pip install -r app/requirements.txt`

**Run**
- `python app/signaling_server.py`

**Key environment variables**
- `RC_SIGNALING_HOST`, `RC_SIGNALING_PORT`
- `RC_DATABASE_URL`
- `RC_SIGNALING_TOKEN`, `RC_API_TOKEN`
- `RC_ICE_SERVERS`
