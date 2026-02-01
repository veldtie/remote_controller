# signaling_server.py
# WebRTC signaling server for Remote Desktop

import logging
import logging.handlers
import os
from pathlib import Path

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOGGING_CONFIGURED = False


def _resolve_level(value: str | None, fallback: int) -> int:
    if not value:
        return fallback
    level = logging.getLevelName(value.upper())
    return level if isinstance(level, int) else fallback


def _default_error_log_file() -> str:
    if os.name != "nt" and Path("/data").exists():
        return "/data/logs/signaling-error.log"
    return "logs/signaling-error.log"


def _configure_logging() -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return
    _LOGGING_CONFIGURED = True

    log_level = _resolve_level(os.getenv("RC_LOG_LEVEL", "INFO"), logging.INFO)
    logging.basicConfig(level=log_level, format=LOG_FORMAT)

    error_log_file = os.getenv("RC_ERROR_LOG_FILE", _default_error_log_file()).strip()
    if not error_log_file:
        return

    error_level = _resolve_level(os.getenv("RC_ERROR_LOG_LEVEL", "WARNING"), logging.WARNING)
    max_bytes = int(os.getenv("RC_ERROR_LOG_MAX_BYTES", str(10 * 1024 * 1024)))
    backup_count = int(os.getenv("RC_ERROR_LOG_BACKUP_COUNT", "5"))

    logger = logging.getLogger("signaling_server")
    root_logger = logging.getLogger()
    target_path = os.path.abspath(error_log_file)
    for handler in root_logger.handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler) and (
            os.path.abspath(handler.baseFilename) == target_path
        ):
            return
    try:
        log_path = Path(target_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(error_level)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root_logger.addHandler(file_handler)
    except Exception:
        logger.exception("Failed to configure error log file %s", error_log_file)


_configure_logging()

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
