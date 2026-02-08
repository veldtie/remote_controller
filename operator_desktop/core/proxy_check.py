from __future__ import annotations

import socket
import struct
from typing import Tuple


_REP_MESSAGES = {
    0x01: "General SOCKS server failure",
    0x02: "Connection not allowed",
    0x03: "Network unreachable",
    0x04: "Host unreachable",
    0x05: "Connection refused",
    0x06: "TTL expired",
    0x07: "Command not supported",
    0x08: "Address type not supported",
}


def _recv_exact(sock: socket.socket, count: int) -> bytes:
    data = b""
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise ConnectionError("Socket closed")
        data += chunk
    return data


def _consume_reply_address(sock: socket.socket, atyp: int) -> None:
    if atyp == 0x01:
        _recv_exact(sock, 4)
    elif atyp == 0x03:
        length = _recv_exact(sock, 1)[0]
        if length:
            _recv_exact(sock, length)
    elif atyp == 0x04:
        _recv_exact(sock, 16)
    else:
        raise ValueError(f"Unsupported ATYP {atyp}")
    _recv_exact(sock, 2)


def _normalize_host(value: str) -> str:
    host = (value or "").strip()
    if host.startswith("[") and "]" in host:
        host = host[1 : host.index("]")]
    return host.strip()


def check_socks5_proxy(
    host: str,
    port: int | str,
    timeout: float = 4.0,
    target_host: str = "1.1.1.1",
    target_port: int = 80,
) -> Tuple[bool, str]:
    host = _normalize_host(str(host or ""))
    if not host:
        return False, "Missing proxy host"
    try:
        port_value = int(port)
    except (TypeError, ValueError):
        return False, "Invalid proxy port"
    if port_value <= 0 or port_value > 65535:
        return False, "Invalid proxy port"

    sock = None
    try:
        sock = socket.create_connection((host, port_value), timeout=timeout)
        sock.settimeout(timeout)

        sock.sendall(b"\x05\x01\x00")
        response = _recv_exact(sock, 2)
        if len(response) != 2 or response[0] != 0x05:
            return False, "Invalid SOCKS response"
        if response[1] != 0x00:
            return False, "Authentication required"

        try:
            addr = socket.inet_aton(target_host)
            request = b"\x05\x01\x00\x01" + addr + struct.pack("!H", target_port)
        except OSError:
            target_bytes = target_host.encode("utf-8", errors="ignore")[:255]
            request = (
                b"\x05\x01\x00\x03"
                + bytes([len(target_bytes)])
                + target_bytes
                + struct.pack("!H", target_port)
            )
        sock.sendall(request)
        header = _recv_exact(sock, 4)
        if len(header) != 4 or header[0] != 0x05:
            return False, "Invalid SOCKS reply"
        rep = header[1]
        atyp = header[3]
        try:
            _consume_reply_address(sock, atyp)
        except ValueError:
            return False, "Unsupported reply address"
        if rep != 0x00:
            return False, _REP_MESSAGES.get(rep, f"Connection failed ({rep})")
        return True, "ok"
    except Exception as exc:
        return False, str(exc)
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
