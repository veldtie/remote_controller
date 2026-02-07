"""Minimal SOCKS5 proxy server with UDP associate support."""
from __future__ import annotations

import logging
import select
import socket
import struct
import threading
from dataclasses import dataclass
from typing import Optional, Tuple


logger = logging.getLogger("remote_client.proxy")

SOCKS_VERSION = 5
CMD_CONNECT = 0x01
CMD_UDP_ASSOCIATE = 0x03

REP_SUCCESS = 0x00
REP_GENERAL_FAILURE = 0x01
REP_CMD_NOT_SUPPORTED = 0x07
REP_ATYP_NOT_SUPPORTED = 0x08

ATYP_IPV4 = 0x01
ATYP_DOMAIN = 0x03
ATYP_IPV6 = 0x04


def _recv_exact(sock: socket.socket, count: int) -> bytes:
    data = b""
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise ConnectionError("Socket closed")
        data += chunk
    return data


def _parse_address_from_stream(sock: socket.socket, atyp: int) -> Tuple[str, int]:
    if atyp == ATYP_IPV4:
        addr = socket.inet_ntoa(_recv_exact(sock, 4))
    elif atyp == ATYP_IPV6:
        addr = socket.inet_ntop(socket.AF_INET6, _recv_exact(sock, 16))
    elif atyp == ATYP_DOMAIN:
        length = _recv_exact(sock, 1)[0]
        addr = _recv_exact(sock, length).decode("utf-8", errors="ignore")
    else:
        raise ValueError("Unsupported address type")
    port = struct.unpack("!H", _recv_exact(sock, 2))[0]
    return addr, port


def _pack_address(addr: str) -> Tuple[int, bytes]:
    try:
        packed = socket.inet_aton(addr)
        return ATYP_IPV4, packed
    except OSError:
        pass
    try:
        packed = socket.inet_pton(socket.AF_INET6, addr)
        return ATYP_IPV6, packed
    except OSError:
        pass
    addr_bytes = addr.encode("utf-8", errors="ignore")
    if len(addr_bytes) > 255:
        addr_bytes = addr_bytes[:255]
    return ATYP_DOMAIN, bytes([len(addr_bytes)]) + addr_bytes


def _send_reply(sock: socket.socket, rep: int, bind_addr: str, bind_port: int) -> None:
    atyp, addr_bytes = _pack_address(bind_addr)
    reply = struct.pack("!BBBB", SOCKS_VERSION, rep, 0x00, atyp)
    reply += addr_bytes + struct.pack("!H", bind_port)
    sock.sendall(reply)


@dataclass
class ProxyStats:
    tcp_bytes_up: int = 0
    tcp_bytes_down: int = 0
    udp_packets_in: int = 0
    udp_packets_out: int = 0


class Socks5ProxyServer:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 1080,
        enable_udp: bool = True,
        backlog: int = 128,
    ) -> None:
        self.host = host or "0.0.0.0"
        self.port = int(port)
        self.enable_udp = bool(enable_udp)
        self.backlog = max(1, int(backlog))
        self._tcp_sock: Optional[socket.socket] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._tcp_sock:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(self.backlog)
        sock.settimeout(1.0)
        self._tcp_sock = sock
        self.port = sock.getsockname()[1]
        self._stop_event.clear()
        self._accept_thread = threading.Thread(
            target=self._accept_loop, name="socks5-accept", daemon=True
        )
        self._accept_thread.start()
        logger.info(
            "SOCKS5 proxy listening on %s:%s (udp=%s)",
            self.host,
            self.port,
            self.enable_udp,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._tcp_sock:
            try:
                self._tcp_sock.close()
            except OSError:
                pass
        self._tcp_sock = None

    def _accept_loop(self) -> None:
        if not self._tcp_sock:
            return
        while not self._stop_event.is_set():
            try:
                conn, addr = self._tcp_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(
                target=self._handle_client,
                args=(conn, addr),
                name=f"socks5-client-{addr[0]}:{addr[1]}",
                daemon=True,
            ).start()

    def _handle_client(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        conn_id = f"{addr[0]}:{addr[1]}"
        stats = ProxyStats()
        try:
            conn.settimeout(10.0)
            if not self._handle_handshake(conn):
                return
            request = _recv_exact(conn, 4)
            ver, cmd, _rsv, atyp = request
            if ver != SOCKS_VERSION:
                return
            try:
                dest_addr, dest_port = _parse_address_from_stream(conn, atyp)
            except ValueError:
                _send_reply(conn, REP_ATYP_NOT_SUPPORTED, "0.0.0.0", 0)
                return
            if cmd == CMD_CONNECT:
                self._handle_connect(conn, conn_id, dest_addr, dest_port, stats)
            elif cmd == CMD_UDP_ASSOCIATE:
                if not self.enable_udp:
                    _send_reply(conn, REP_CMD_NOT_SUPPORTED, "0.0.0.0", 0)
                    return
                self._handle_udp_associate(conn, conn_id, addr, dest_addr, dest_port, stats)
            else:
                _send_reply(conn, REP_CMD_NOT_SUPPORTED, "0.0.0.0", 0)
        except Exception as exc:
            logger.debug("SOCKS5 client %s error: %s", conn_id, exc)
        finally:
            try:
                conn.close()
            except OSError:
                pass
            if stats.tcp_bytes_up or stats.tcp_bytes_down:
                logger.info(
                    "SOCKS5 %s closed (tcp_up=%s tcp_down=%s)",
                    conn_id,
                    stats.tcp_bytes_up,
                    stats.tcp_bytes_down,
                )

    def _handle_handshake(self, conn: socket.socket) -> bool:
        header = _recv_exact(conn, 2)
        ver, n_methods = header
        if ver != SOCKS_VERSION:
            return False
        methods = _recv_exact(conn, n_methods)
        if 0x00 not in methods:
            conn.sendall(struct.pack("!BB", SOCKS_VERSION, 0xFF))
            return False
        conn.sendall(struct.pack("!BB", SOCKS_VERSION, 0x00))
        return True

    def _handle_connect(
        self,
        conn: socket.socket,
        conn_id: str,
        dest_addr: str,
        dest_port: int,
        stats: ProxyStats,
    ) -> None:
        try:
            remote = socket.create_connection((dest_addr, dest_port), timeout=10.0)
        except OSError as exc:
            logger.info("SOCKS5 %s connect failed to %s:%s (%s)", conn_id, dest_addr, dest_port, exc)
            _send_reply(conn, REP_GENERAL_FAILURE, "0.0.0.0", 0)
            return
        try:
            local_addr, local_port = remote.getsockname()
            _send_reply(conn, REP_SUCCESS, local_addr, local_port)
            logger.info("SOCKS5 %s connected to %s:%s", conn_id, dest_addr, dest_port)
            self._relay_tcp(conn, remote, stats)
        finally:
            try:
                remote.close()
            except OSError:
                pass

    def _relay_tcp(self, client: socket.socket, remote: socket.socket, stats: ProxyStats) -> None:
        client.settimeout(None)
        remote.settimeout(None)
        sockets = [client, remote]
        while True:
            readable, _, _ = select.select(sockets, [], [], 60)
            if not readable:
                continue
            for sock in readable:
                try:
                    data = sock.recv(65535)
                except OSError:
                    return
                if not data:
                    return
                if sock is client:
                    remote.sendall(data)
                    stats.tcp_bytes_up += len(data)
                else:
                    client.sendall(data)
                    stats.tcp_bytes_down += len(data)

    def _handle_udp_associate(
        self,
        conn: socket.socket,
        conn_id: str,
        peer_addr: Tuple[str, int],
        req_addr: str,
        req_port: int,
        stats: ProxyStats,
    ) -> None:
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.bind((self.host, 0))
        bind_addr, bind_port = udp_sock.getsockname()
        local_ip = conn.getsockname()[0]
        reply_ip = local_ip if local_ip and local_ip != "0.0.0.0" else bind_addr
        _send_reply(conn, REP_SUCCESS, reply_ip, bind_port)
        logger.info(
            "SOCKS5 %s UDP associate ready on %s:%s",
            conn_id,
            reply_ip,
            bind_port,
        )
        stop_event = threading.Event()
        udp_thread = threading.Thread(
            target=self._udp_relay_loop,
            args=(udp_sock, peer_addr[0], stop_event, stats, conn_id),
            name=f"socks5-udp-{conn_id}",
            daemon=True,
        )
        udp_thread.start()
        try:
            conn.settimeout(1.0)
            while True:
                try:
                    data = conn.recv(1)
                except socket.timeout:
                    if self._stop_event.is_set():
                        break
                    continue
                if not data:
                    break
        finally:
            stop_event.set()
            try:
                udp_sock.close()
            except OSError:
                pass

    def _udp_relay_loop(
        self,
        udp_sock: socket.socket,
        client_ip: str,
        stop_event: threading.Event,
        stats: ProxyStats,
        conn_id: str,
    ) -> None:
        udp_sock.settimeout(1.0)
        client_addr: Optional[Tuple[str, int]] = None
        while not stop_event.is_set():
            try:
                data, addr = udp_sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                continue
            if addr[0] == client_ip:
                client_addr = addr
                if len(data) < 4:
                    continue
                rsv = data[:2]
                frag = data[2]
                atyp = data[3]
                if rsv != b"\x00\x00" or frag != 0x00:
                    continue
                offset = 4
                try:
                    if atyp == ATYP_IPV4:
                        if len(data) < offset + 4:
                            continue
                        target_addr = socket.inet_ntoa(data[offset : offset + 4])
                        offset += 4
                    elif atyp == ATYP_IPV6:
                        if len(data) < offset + 16:
                            continue
                        target_addr = socket.inet_ntop(
                            socket.AF_INET6, data[offset : offset + 16]
                        )
                        offset += 16
                    elif atyp == ATYP_DOMAIN:
                        if len(data) < offset + 1:
                            continue
                        length = data[offset]
                        offset += 1
                        if len(data) < offset + length:
                            continue
                        target_addr = data[offset : offset + length].decode(
                            "utf-8", errors="ignore"
                        )
                        offset += length
                    else:
                        continue
                    if len(data) < offset + 2:
                        continue
                    target_port = struct.unpack("!H", data[offset : offset + 2])[0]
                    offset += 2
                    payload = data[offset:]
                except Exception:
                    continue
                try:
                    udp_sock.sendto(payload, (target_addr, target_port))
                    stats.udp_packets_out += 1
                except OSError:
                    continue
            else:
                if client_addr is None:
                    continue
                atyp, addr_bytes = _pack_address(addr[0])
                header = struct.pack("!HBB", 0x0000, 0x00, atyp) + addr_bytes
                header += struct.pack("!H", addr[1])
                try:
                    udp_sock.sendto(header + data, client_addr)
                    stats.udp_packets_in += 1
                except OSError:
                    continue
        if stats.udp_packets_in or stats.udp_packets_out:
            logger.info(
                "SOCKS5 %s UDP closed (in=%s out=%s)",
                conn_id,
                stats.udp_packets_in,
                stats.udp_packets_out,
            )
