# signaling_server.py
# WebRTC signaling server for Remote Desktop

import logging
import os

logging.basicConfig(
    level=os.getenv("RC_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

import signaling_config as config
from signaling_routes import router as api_router
from signaling_ws import router as ws_router, start_background_tasks, stop_background_tasks

app = FastAPI()

# Allow browser clients opened from file:// or other origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ws_router)


@app.on_event("startup")
async def _start_background_tasks() -> None:
    await start_background_tasks()


@app.on_event("shutdown")
async def _stop_background_tasks() -> None:
    await stop_background_tasks()


if __name__ == "__main__":
    uvicorn.run(app, host=config.SIGNALING_HOST, port=config.SIGNALING_PORT)
