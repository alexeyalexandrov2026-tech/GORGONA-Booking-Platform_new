"""AMARKAL Fail-Closed ClamAV HTTP Scanner Service for Cloud Run (ADR-0020).

Implements POST /scan accepting raw bytes and returning:
  {"clean": true} or {"clean": false, "signature": "..."}
Authenticated via constant-time Bearer token (SCANNER_AUTH_TOKEN).
"""

from __future__ import annotations

import hmac
import json
import os
import socket
import struct
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB hard cap
CLAMD_HOST = os.environ.get("CLAMD_HOST", "127.0.0.1")
CLAMD_PORT = int(os.environ.get("CLAMD_PORT", "3310"))
AUTH_TOKEN = os.environ.get("SCANNER_AUTH_TOKEN", "").strip()


def scan_via_clamd(payload: bytes) -> tuple[bool, str | None]:
    """Stream bytes to local clamd over TCP INSTREAM; fail closed on any error."""
    with socket.create_connection((CLAMD_HOST, CLAMD_PORT), timeout=15.0) as sock:
        sock.sendall(b"zINSTREAM\0")
        chunk_size = 65536
        for idx in range(0, len(payload), chunk_size):
            chunk = payload[idx : idx + chunk_size]
            sock.sendall(struct.pack("!I", len(chunk)) + chunk)
        sock.sendall(struct.pack("!I", 0))

        chunks: list[bytes] = []
        while True:
            data = sock.recv(4096)
            if not data:
                break
            chunks.append(data)
            if b"\0" in data:
                break
        reply = b"".join(chunks).split(b"\0", 1)[0].decode("utf-8", errors="replace").strip()

    if reply.endswith("OK"):
        return True, None
    if "FOUND" in reply:
        sig = reply.removeprefix("stream:").removesuffix("FOUND").strip()
        return False, sig or "MALWARE_SIGNATURE"
    raise RuntimeError(f"Unexpected clamd verdict: {reply}")


def ping_clamd() -> bool:
    try:
        with socket.create_connection((CLAMD_HOST, CLAMD_PORT), timeout=3.0) as sock:
            sock.sendall(b"zPING\0")
            return sock.recv(64).startswith(b"PONG")
    except OSError:
        return False


class ScannerHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def _send_json(self, code: int, body: dict[str, object]) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            ok = ping_clamd()
            self._send_json(200 if ok else 503, {"status": "ready" if ok else "starting"})
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/scan":
            self._send_json(404, {"error": "not_found"})
            return
        if not AUTH_TOKEN:
            self._send_json(503, {"error": "scanner_token_not_configured"})
            return
        auth = self.headers.get("Authorization", "")
        expected = f"Bearer {AUTH_TOKEN}"
        if not hmac.compare_digest(auth, expected):
            self._send_json(401, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"error": "invalid_content_length"})
            return
        if length < 0 or length > MAX_UPLOAD_BYTES:
            self._send_json(413, {"error": "payload_too_large"})
            return

        payload = self.rfile.read(length) if length > 0 else b""
        try:
            clean, signature = scan_via_clamd(payload)
        except Exception:
            self._send_json(503, {"error": "scanner_unavailable"})
            return
        result: dict[str, object] = {"clean": clean}
        if signature:
            result["signature"] = signature
        self._send_json(200, result)


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), ScannerHandler)  # noqa: S104
    server.serve_forever()


if __name__ == "__main__":
    main()
