# signaling_server.py
# WebRTC signaling server for Remote Desktop

import asyncio
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from aiortc import RTCSessionDescription
from aiortc.contrib.signaling import TcpSocketSignaling
import uvicorn

app = FastAPI()

SIGNALING_HOST = os.getenv("RC_SIGNALING_HOST", "0.0.0.0")
SIGNALING_PORT = int(os.getenv("RC_SIGNALING_PORT", "9999"))
SIGNALING_CONNECT_TIMEOUT = float(os.getenv("RC_SIGNALING_CONNECT_TIMEOUT", "30"))
SIGNALING_ANSWER_TIMEOUT = float(os.getenv("RC_SIGNALING_ANSWER_TIMEOUT", "30"))

# Allow browser clients opened from file:// or other origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# TCP signaling used by Python client
signaling = TcpSocketSignaling(SIGNALING_HOST, SIGNALING_PORT)
signaling_lock = asyncio.Lock()

@app.post("/offer")
async def offer(request: Request):
    data = await request.json()
    offer = RTCSessionDescription(sdp=data["sdp"], type=data["type"])

    async with signaling_lock:
        try:
            await asyncio.wait_for(signaling.send(offer), timeout=SIGNALING_CONNECT_TIMEOUT)
            answer = await asyncio.wait_for(
                signaling.receive(),
                timeout=SIGNALING_ANSWER_TIMEOUT,
            )
        except asyncio.TimeoutError:
            return JSONResponse(
                {"error": "Timed out waiting for the remote client."},
                status_code=504,
            )
        except (ConnectionError, OSError) as exc:
            return JSONResponse(
                {"error": f"Signaling connection failed: {exc}"},
                status_code=502,
            )
        finally:
            await signaling.close()

    if answer is None:
        return JSONResponse(
            {"error": "Remote client disconnected before sending an answer."},
            status_code=502,
        )

    return JSONResponse({"sdp": answer.sdp, "type": answer.type})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
