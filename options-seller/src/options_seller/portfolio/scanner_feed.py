"""Load scanner candidates — local file primary, remote optional (IPv4).

On this shared box, *.trycloudflare.com may NXDOMAIN / fail on IPv6.
Default data source is the local scan file. Remote is best-effort via
IPv4 (curl -4) and never surfaces DNS failure as an error when local works.

Env:
  SCANNER_BASE_URL  — https://views-pill-radical-templates.trycloudflare.com
  SCANNER_UI_URL    — browser link (defaults to BASE)
  SCANNER_JSON_URL  — explicit JSON URL override
  SCANNER_JSON_PATH — local file (default /workspace/stock-data-scanner/scan-latest.json)

Remote paths when reachable: {BASE}/scan-latest.json , {BASE}/api/scan
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from options_seller.config import load_defaults
from options_seller.models.scanner import PortfolioContext, ScanEnvelope
from options_seller.selector import Selection, select_and_build
from options_seller.strategies.base import should_skip_earnings

DEFAULT_SCANNER_BASE_URL = "https://views-pill-radical-templates.trycloudflare.com"
DEFAULT_SCANNER_JSON_PATH = Path(__file__).resolve().parents[4] / "stock-data-scanner" / "scan-latest.json"
FALLBACK_SCAN_PATH = Path(__file__).resolve().parents[3] / "examples" / "scan-latest.json"
REMOTE_JSON_PATHS = ("/api/scan", "/scan-latest.json")


def scanner_base_url() -> str:
    return os.environ.get("SCANNER_BASE_URL", DEFAULT_SCANNER_BASE_URL).rstrip("/")


def scanner_ui_url() -> str:
    return os.environ.get("SCANNER_UI_URL", scanner_base_url()).rstrip("/")


def scanner_json_path() -> Path:
    raw = os.environ.get("SCANNER_JSON_PATH")
    return Path(raw) if raw else DEFAULT_SCANNER_JSON_PATH


def scanner_json_url() -> Optional[str]:
    url = os.environ.get("SCANNER_JSON_URL", "").strip()
    return url or None


def remote_json_candidates() -> list[str]:
    explicit = scanner_json_url()
    if explicit:
        return [explicit]
    base = scanner_base_url()
    if not base:
        return []
    return [f"{base}{p}" for p in REMOTE_JSON_PATHS]


def _read_json_file(path: Path) -> Optional[dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _fetch_json_curl4(url: str, timeout: float = 4.0) -> Optional[dict[str, Any]]:
    """Fetch JSON forcing IPv4 via curl -4 (Cloudflare edge often IPv4-only here)."""
    try:
        proc = subprocess.run(
            [
                "curl",
                "-4",
                "-fsS",
                "-L",
                "--max-time",
                str(int(timeout)),
                "-H",
                "Accept: application/json",
                "-H",
                "User-Agent: options-seller-dashboard/0.1",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=timeout + 2,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout:
            return None
        body = proc.stdout.lstrip()
        if body.startswith("<!") or body.lower().startswith("<html"):
            return None
        data = json.loads(body)
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _fetch_json_urllib_ipv4(url: str, timeout: float = 4.0) -> Optional[dict[str, Any]]:
    """urllib fallback; prefer A-record by resolving hostname to IPv4 when possible."""
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            return None
        ipv4 = None
        try:
            infos = socket.getaddrinfo(host, parsed.port or 443, socket.AF_INET, socket.SOCK_STREAM)
            if infos:
                ipv4 = infos[0][4][0]
        except OSError:
            ipv4 = None

        headers = {
            "Accept": "application/json",
            "User-Agent": "options-seller-dashboard/0.1",
        }
        if ipv4:
            # Host header required when addressing by IP
            headers["Host"] = host
            netloc = ipv4
            if parsed.port:
                netloc = f"{ipv4}:{parsed.port}"
            fetch_url = urlunparse(
                (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
            )
        else:
            fetch_url = url

        req = urllib.request.Request(fetch_url, headers=headers)
        # For HTTPS to IP with Host header, context may still fail SNI — that's ok,
        # curl -4 is primary. This path helps plain http / when resolve works.
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            body = resp.read().decode("utf-8")
        stripped = body.lstrip()
        if stripped.startswith("<!") or stripped.lower().startswith("<html"):
            return None
        if "html" in ctype and "json" not in ctype:
            return None
        data = json.loads(body)
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _fetch_json_url(url: str, timeout: float = 4.0) -> Optional[dict[str, Any]]:
    """Best-effort remote fetch: curl -4 first, then urllib."""
    data = _fetch_json_curl4(url, timeout=timeout)
    if data is not None:
        return data
    return _fetch_json_urllib_ipv4(url, timeout=timeout)


def load_scan_envelope(
    *,
    path: Path | None = None,
    try_remote: bool = True,
) -> tuple[Optional[ScanEnvelope], dict[str, Any]]:
    """Load scan JSON — **local file first**, then optional remote (IPv4), then examples.

    Remote DNS/NXDOMAIN/IPv6 failure is NOT an error when local file works.
    """
    file_path = Path(path) if path else scanner_json_path()
    status: dict[str, Any] = {
        "ui_url": scanner_ui_url(),
        "base_url": scanner_base_url(),
        "json_path": str(file_path),
        "json_url": scanner_json_url(),
        "remote_tried": [],
        "remote_ok": False,
        "local_ok": False,
        "source": None,
        "source_kind": None,
        "as_of": None,
        "ok": False,
        "error": None,
        "n_results": 0,
        "remote_note": None,
    }

    raw: Optional[dict[str, Any]] = None

    # 1) Primary: local file on shared box
    raw = _read_json_file(file_path)
    if raw is not None:
        status["source"] = f"file:{file_path}"
        status["source_kind"] = "local"
        status["local_ok"] = True

    # 2) Optional remote (IPv4); only used when local missing
    if try_remote and raw is None:
        for url in remote_json_candidates():
            status["remote_tried"].append(url)
            remote_raw = _fetch_json_url(url)
            if remote_raw is not None:
                status["remote_ok"] = True
                status["json_url"] = url
                raw = remote_raw
                status["source"] = f"remote:{url}"
                status["source_kind"] = "remote"
                break
        if status["remote_tried"] and not status["remote_ok"]:
            status["remote_note"] = "remote unreachable — using local/fallback"

    elif try_remote and raw is not None:
        # Do NOT probe remote on every load — that can hang DNS/curl and leave
        # Streamlit "Running…" for tens of seconds. Refresh uses refresh_scan_data().
        status["remote_note"] = "local file used (remote probe skipped; use Refresh scan data)"

    # 3) Examples fallback
    if raw is None and FALLBACK_SCAN_PATH.exists():
        raw = _read_json_file(FALLBACK_SCAN_PATH)
        if raw is not None:
            status["source"] = f"file:{FALLBACK_SCAN_PATH} (fallback)"
            status["source_kind"] = "fallback"
            status["json_path"] = str(FALLBACK_SCAN_PATH)

    if raw is None:
        status["error"] = "No scan JSON at local path (and remote unreachable)"
        return None, status

    try:
        envelope = ScanEnvelope.load(raw)
    except Exception as exc:  # noqa: BLE001
        status["error"] = f"Failed to parse scan envelope: {exc}"
        return None, status

    status["ok"] = True
    status["as_of"] = envelope.asOf
    status["n_results"] = len(envelope.results)
    status["schema"] = envelope.schema_
    return envelope, status


def refresh_scan_data(
    *,
    path: Path | None = None,
    timeout: float = 1.5,
) -> tuple[Optional[ScanEnvelope], dict[str, Any], dict[str, Any]]:
    """Fast refresh for Command Center — poll JSON API or re-read local file.

    Never triggers Yahoo / scanner recompute. Prefer ``/api/scan`` with a short
    timeout; on success write through to the local scan file so subsequent loads
    stay local-only. Falls back to local file if remote is slow/unreachable.
    """
    import time

    t0 = time.perf_counter()
    file_path = Path(path) if path else scanner_json_path()
    meta: dict[str, Any] = {
        "polled_remote": False,
        "wrote_local": False,
        "elapsed_ms": 0,
        "mode": "local",
    }

    # 1) Quick remote poll (JSON only) — prefer /api/scan
    remote_raw = None
    for url in remote_json_candidates():
        meta["polled_remote"] = True
        remote_raw = _fetch_json_url(url, timeout=timeout)
        if remote_raw is not None:
            meta["mode"] = "remote_poll"
            meta["url"] = url
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(json.dumps(remote_raw, indent=2), encoding="utf-8")
                meta["wrote_local"] = True
            except OSError as exc:
                meta["write_error"] = str(exc)
            break

    # 2) Always load via local-first path with remote probe disabled
    envelope, status = load_scan_envelope(path=file_path, try_remote=False)
    meta["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    if envelope is None and remote_raw is None:
        meta["mode"] = "failed"
    elif not meta.get("wrote_local"):
        meta["mode"] = "local"
    status["refresh_meta"] = meta
    return envelope, status, meta



def build_candidates(
    envelope: ScanEnvelope,
    *,
    portfolio: PortfolioContext | None = None,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    cfg = cfg or load_defaults()
    portfolio = portfolio or PortfolioContext()
    rows: list[dict[str, Any]] = []
    for scan in envelope.results:
        sel: Optional[Selection] = select_and_build(scan, cfg, portfolio)
        row: dict[str, Any] = {
            "symbol": scan.symbol,
            "name": scan.name,
            "price": scan.price,
            "bias": scan.bias.value if scan.bias else None,
            "iv_rank": scan.iv_rank,
            "days_to_earnings": scan.days_to_earnings,
            "strategy": None,
            "reason": None,
            "is_template": None,
            "net_premium": None,
            "max_profit": None,
            "max_loss": None,
            "capital": None,
            "target_dte": None,
            "notes": None,
            "plan": None,
            "skipped": sel is None,
            "skip_reason": None,
        }
        if sel is None:
            if should_skip_earnings(scan, cfg):
                dte = scan.days_to_earnings
                row["skip_reason"] = (
                    f"earnings in {dte}d — skipped by rule" if dte is not None
                    else "earnings upcoming — skipped by rule"
                )
            elif scan.price is None:
                row["skip_reason"] = "no price in scan"
            else:
                row["skip_reason"] = "no strategy matched this scan"
        else:
            plan = sel.result.plan
            row.update(
                {
                    "strategy": sel.strategy_name,
                    "reason": sel.reason,
                    "is_template": plan.is_template,
                    "net_premium": plan.net_premium,
                    "max_profit": plan.max_profit,
                    "max_loss": plan.max_loss,
                    "capital": plan.capital_required,
                    "target_dte": plan.target_dte,
                    "notes": plan.notes,
                    "plan": plan,
                    "skipped": False,
                }
            )
        rows.append(row)
    return rows
