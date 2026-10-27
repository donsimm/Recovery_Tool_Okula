"""Steuer- und Datenverbindung Tool ↔ Agent: TLS 1.3 mit vorab geteiltem Schlüssel (PSK).

Der Schlüssel wird beim Erstellen des Agent-Sticks eingebettet; ein Agent mit
fremdem Schlüssel scheitert schon am TLS-Handshake. Nachrichten sind Frames:
1 Byte Typ (J = JSON, D = Daten) + 4 Byte Länge (big endian) + Nutzlast.
Nur stdlib, läuft auch auf dem Stick.
"""

from __future__ import annotations

import json
import socket
import ssl
import struct

PORT = 47812
PSK_IDENTITY = "okula-recovery"
KEY_LEN = 32
FRAME_JSON = b"J"
FRAME_DATA = b"D"
MAX_FRAME = 8 * 1024 * 1024
CHUNK = 1024 * 1024

_HEADER = struct.Struct(">cI")


class ProtocolError(Exception):
    pass


def _base_context(protocol: int) -> ssl.SSLContext:
    ctx = ssl.SSLContext(protocol)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    return ctx


def server_context(key: bytes) -> ssl.SSLContext:
    ctx = _base_context(ssl.PROTOCOL_TLS_SERVER)
    ctx.set_psk_server_callback(lambda identity: key if identity == PSK_IDENTITY else b"")
    return ctx


def client_context(key: bytes) -> ssl.SSLContext:
    ctx = _base_context(ssl.PROTOCOL_TLS_CLIENT)
    # Authentisierung über den PSK, es gibt keine Zertifikate
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_psk_client_callback(lambda hint: (PSK_IDENTITY, key))
    return ctx


def connect(host: str, key: bytes, port: int = PORT, timeout: float = 15.0) -> ssl.SSLSocket:
    raw = socket.create_connection((host, port), timeout=timeout)
    try:
        return client_context(key).wrap_socket(raw)
    except Exception:
        raw.close()
        raise


def send_json(sock: socket.socket, obj: dict) -> None:
    payload = json.dumps(obj, ensure_ascii=False).encode()
    sock.sendall(_HEADER.pack(FRAME_JSON, len(payload)) + payload)


def send_data(sock: socket.socket, data: bytes) -> None:
    sock.sendall(_HEADER.pack(FRAME_DATA, len(data)) + data)


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(min(n - len(buf), CHUNK))
        if not chunk:
            raise ProtocolError("Verbindung unerwartet beendet")
        buf += chunk
    return bytes(buf)


def recv_frame(sock: socket.socket) -> tuple[bytes, dict | bytes]:
    kind, length = _HEADER.unpack(_recv_exact(sock, _HEADER.size))
    if length > MAX_FRAME:
        raise ProtocolError(f"Frame zu gross ({length} Bytes)")
    payload = _recv_exact(sock, length)
    if kind == FRAME_JSON:
        try:
            obj = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ProtocolError(f"Ungültiges JSON: {e}") from None
        if not isinstance(obj, dict):
            raise ProtocolError("JSON-Frame ist kein Objekt")
        return kind, obj
    if kind == FRAME_DATA:
        return kind, payload
    raise ProtocolError(f"Unbekannter Frame-Typ {kind!r}")


def recv_json(sock: socket.socket) -> dict:
    kind, payload = recv_frame(sock)
    if kind != FRAME_JSON:
        raise ProtocolError("JSON erwartet, Daten erhalten")
    return payload  # type: ignore[return-value]
