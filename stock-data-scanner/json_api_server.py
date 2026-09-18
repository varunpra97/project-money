#!/usr/bin/env python3
"""Tiny JSON API for scan-latest.json on port 8502."""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(os.environ.get("JSON_API_PORT", "8502"))
SCAN_PATH = Path(
    os.environ.get(
        "SCAN_LATEST_PATH",
        str(Path(__file__).resolve().parent / "scan-latest.json"),
    )
)
JSON_PATHS = {"/api/scan", "/api/scan/", "/scan-latest.json"}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[json-api] {self.address_string()} - {fmt % args}")

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_HEAD(self) -> None:
        self._serve(include_body=False)

    def do_GET(self) -> None:
        self._serve(include_body=True)

    def _serve(self, include_body: bool = True) -> None:
        path = self.path.split("?", 1)[0]
        if path not in JSON_PATHS:
            body = b'{"error":"not found"}'
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if include_body:
                self.wfile.write(body)
            return

        if not SCAN_PATH.is_file():
            body = b'{"error":"scan not ready"}'
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if include_body:
                self.wfile.write(body)
            return

        try:
            raw = SCAN_PATH.read_bytes()
            json.loads(raw)
        except (OSError, json.JSONDecodeError):
            body = b'{"error":"scan not ready"}'
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if include_body:
                self.wfile.write(body)
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if include_body:
            self.wfile.write(raw)


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[json-api] serving {SCAN_PATH} on 0.0.0.0:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
