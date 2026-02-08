import socket
import struct
import threading

from remote_client.proxy.socks5_server import Socks5ProxyServer


def _recv_exact(sock: socket.socket, count: int) -> bytes:
    data = b""
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise ConnectionError("socket closed")
        data += chunk
    return data


def _start_echo_server() -> tuple[int, threading.Thread]:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    ready = threading.Event()

    def _run() -> None:
        ready.set()
        server.settimeout(2.0)
        try:
            conn, _addr = server.accept()
        except socket.timeout:
            server.close()
            return
        with conn:
            conn.settimeout(2.0)
            data = conn.recv(1024)
            if data:
                conn.sendall(data)
        server.close()

    thread = threading.Thread(target=_run, name="echo-server", daemon=True)
    thread.start()
    ready.wait(2.0)
    return port, thread


def _socks5_connect(proxy_host: str, proxy_port: int, dest_host: str, dest_port: int) -> socket.socket:
    sock = socket.create_connection((proxy_host, proxy_port), timeout=3.0)
    sock.settimeout(3.0)
    sock.sendall(b"\x05\x01\x00")
    response = _recv_exact(sock, 2)
    assert response == b"\x05\x00"

    addr_bytes = socket.inet_aton(dest_host)
    request = b"\x05\x01\x00\x01" + addr_bytes + struct.pack("!H", dest_port)
    sock.sendall(request)
    header = _recv_exact(sock, 4)
    ver, rep, _rsv, atyp = header
    assert ver == 5
    assert rep == 0
    if atyp == 0x01:
        _recv_exact(sock, 4)
    elif atyp == 0x03:
        length = _recv_exact(sock, 1)[0]
        _recv_exact(sock, length)
    elif atyp == 0x04:
        _recv_exact(sock, 16)
    else:
        raise AssertionError(f"Unexpected ATYP {atyp}")
    _recv_exact(sock, 2)
    return sock


def test_socks5_proxy_connects_to_local_echo() -> None:
    echo_port, echo_thread = _start_echo_server()
    proxy = Socks5ProxyServer(host="127.0.0.1", port=0, enable_udp=False)
    proxy.start()
    try:
        sock = _socks5_connect("127.0.0.1", proxy.port, "127.0.0.1", echo_port)
        with sock:
            sock.sendall(b"ping")
            response = _recv_exact(sock, 4)
        assert response == b"ping"
    finally:
        proxy.stop()
        echo_thread.join(timeout=2.0)
