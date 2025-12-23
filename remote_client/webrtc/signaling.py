"""Signaling helpers for the WebRTC client."""
from __future__ import annotations

from aiortc.contrib.signaling import TcpSocketSignaling


def create_signaling(host: str, port: int) -> TcpSocketSignaling:
    return TcpSocketSignaling(host, port)
