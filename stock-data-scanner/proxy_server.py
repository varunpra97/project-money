#!/usr/bin/env python3
"""Reverse proxy with WebSocket support for Streamlit behind Cloudflare Tunnel.

Routes:
  /api/scan, /api/scan/, /scan-latest.json  -> 127.0.0.1:8502 (JSON API)
  everything else                          -> 127.0.0.1:8501 (Streamlit + WS)
"""
from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import (
    ClientSession,
    ClientTimeout,
    ClientWebSocketResponse,
    WSMsgType,
    web,
)

LISTEN_HOST = os.environ.get("PROXY_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("PROXY_PORT", "8080"))
STREAMLIT = os.environ.get("STREAMLIT_UPSTREAM", "http://127.0.0.1:8501")
JSON_API = os.environ.get("JSON_API_UPSTREAM", "http://127.0.0.1:8502")

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}

log = logging.getLogger("proxy")


def pick_upstream(path: str) -> str:
    p = path.split("?", 1)[0]
    if p == "/scan-latest.json" or p == "/api/scan" or p.startswith("/api/scan/"):
        return JSON_API
    return STREAMLIT


def filter_request_headers(headers) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in headers.items():
        if k.lower() in HOP_BY_HOP:
            continue
        out[k] = v
    return out


def filter_response_headers(headers) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in headers.items():
        if k.lower() in HOP_BY_HOP or k.lower() == "content-encoding":
            # Let aiohttp re-encode / set Content-Length as needed
            continue
        out[k] = v
    return out


async def http_proxy(request: web.Request) -> web.StreamResponse:
    upstream_base = pick_upstream(request.path)
    url = f"{upstream_base}{request.path_qs}"
    headers = filter_request_headers(request.headers)
    body = await request.read() if request.can_read_body else None

    session: ClientSession = request.app["session"]
    try:
        async with session.request(
            request.method,
            url,
            headers=headers,
            data=body,
            allow_redirects=False,
        ) as resp:
            out_headers = filter_response_headers(resp.headers)
            response = web.StreamResponse(status=resp.status, headers=out_headers)
            await response.prepare(request)
            async for chunk in resp.content.iter_chunked(65536):
                await response.write(chunk)
            await response.write_eof()
            return response
    except Exception as exc:
        log.warning("HTTP proxy error %s %s: %s", request.method, url, exc)
        return web.json_response(
            {"error": "upstream unavailable", "detail": str(exc)},
            status=502,
        )


async def _pump(src, dst, label: str) -> None:
    """Copy WS messages from src to dst until closed."""
    try:
        async for msg in src:
            if msg.type in (WSMsgType.TEXT, WSMsgType.BINARY):
                await dst.send_str(msg.data) if msg.type == WSMsgType.TEXT else await dst.send_bytes(msg.data)
            elif msg.type == WSMsgType.PING:
                await dst.ping(msg.data)
            elif msg.type == WSMsgType.PONG:
                await dst.pong(msg.data)
            elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                break
            elif msg.type == WSMsgType.ERROR:
                log.warning("WS %s error: %s", label, src.exception())
                break
    except Exception as exc:
        log.debug("WS pump %s ended: %s", label, exc)


async def websocket_proxy(request: web.Request) -> web.WebSocketResponse:
    """Proxy a WebSocket, preserving Sec-WebSocket-Protocol both ways.

    Streamlit clients offer protocols like ``streamlit`` plus a versioned token
    (``2|...``). aiohttp's WebSocketResponse must be constructed with those
    offered protocols; otherwise prepare() logs
    "Client protocols [...] don't overlap server-known ones ()" and the 101
    response omits Sec-WebSocket-Protocol — browsers then abort the handshake
    and Streamlit stays on the loading skeleton.
    """
    upstream_base = pick_upstream(request.path)
    ws_url = upstream_base.replace("http://", "ws://", 1).replace("https://", "wss://", 1)
    ws_url = f"{ws_url}{request.path_qs}"

    session: ClientSession = request.app["session"]
    headers = filter_request_headers(request.headers)
    raw = request.headers.get("Sec-WebSocket-Protocol")
    offered = [p.strip() for p in raw.split(",") if p.strip()] if raw else []

    # Connect upstream first so we negotiate the same subprotocol Streamlit expects.
    try:
        upstream_ws = await session.ws_connect(
            ws_url,
            headers=headers,
            protocols=offered or (),
            heartbeat=30.0,
            autoping=True,
        )
    except Exception as exc:
        log.warning("WS upstream connect failed %s: %s", ws_url, exc)
        return web.Response(status=502, text="upstream websocket unavailable")

    negotiated = upstream_ws.protocol
    # Accept the browser socket with the negotiated (or offered) protocol so the
    # 101 response includes Sec-WebSocket-Protocol.
    accept_protocols = [negotiated] if negotiated else offered
    client_ws = web.WebSocketResponse(
        protocols=accept_protocols or (),
        autoping=True,
        heartbeat=30.0,
    )
    try:
        await client_ws.prepare(request)
    except Exception as exc:
        log.warning("WS client prepare failed %s: %s", request.path, exc)
        await upstream_ws.close()
        raise

    log.info(
        "WS connected %s -> %s (offered=%s negotiated=%s)",
        request.path,
        ws_url,
        offered,
        negotiated,
    )
    try:
        t1 = asyncio.create_task(_pump(client_ws, upstream_ws, "c2u"))
        t2 = asyncio.create_task(_pump(upstream_ws, client_ws, "u2c"))
        done, pending = await asyncio.wait(
            {t1, t2}, return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()
        for t in done:
            try:
                t.result()
            except Exception:
                pass
    except Exception as exc:
        log.warning("WS proxy error %s: %s", ws_url, exc)
    finally:
        if not upstream_ws.closed:
            await upstream_ws.close()
        if not client_ws.closed:
            await client_ws.close()

    return client_ws


async def handle(request: web.Request) -> web.StreamResponse:
    upgrade = request.headers.get("Upgrade", "").lower()
    if upgrade == "websocket":
        return await websocket_proxy(request)
    return await http_proxy(request)


async def on_startup(app: web.Application) -> None:
    timeout = ClientTimeout(total=None, sock_connect=30, sock_read=None)
    app["session"] = ClientSession(timeout=timeout)


async def on_cleanup(app: web.Application) -> None:
    await app["session"].close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[proxy] %(asctime)s %(levelname)s %(message)s",
    )
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_route("*", "/{path:.*}", handle)
    # Also root
    app.router.add_route("*", "/", handle)

    log.info(
        "0.0.0.0:%s — JSON(/api/scan,/scan-latest.json)->%s else->%s (WS enabled)",
        LISTEN_PORT,
        JSON_API,
        STREAMLIT,
    )
    web.run_app(app, host=LISTEN_HOST, port=LISTEN_PORT, print=lambda *a, **k: None)


if __name__ == "__main__":
    main()
