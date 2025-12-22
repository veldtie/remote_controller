# signaling_server.py
# WebRTC signaling server for Remote Desktop

import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from aiortc import RTCSessionDescription
from aiortc.contrib.signaling import TcpSocketSignaling
import uvicorn

app = FastAPI()

# TCP signaling used by Python client
signaling = TcpSocketSignaling("0.0.0.0", 9999)

@app.on_event("startup")
async def startup():
    await signaling.connect()

@app.post("/offer")
async def offer(request: Request):
    data = await request.json()
    offer = RTCSessionDescription(sdp=data["sdp"], type=data["type"])

    # Send offer to python client
    await signaling.send(offer)

    # Wait for answer
    answer = await signaling.receive()

    return JSONResponse({
        "sdp": answer.sdp,
        "type": answer.type
    })

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
