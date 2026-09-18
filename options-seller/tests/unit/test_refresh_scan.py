"""refresh_scan_data must stay local/JSON-poll fast — never Yahoo."""

from __future__ import annotations

import json
from pathlib import Path

from options_seller.portfolio.scanner_feed import load_scan_envelope, refresh_scan_data


def test_refresh_scan_uses_local_file(tmp_path: Path, monkeypatch):
    scan = {
        "schema": "stock-data-scanner.scan/v0.1",
        "asOf": "2026-09-18T21:00:00Z",
        "source": "test",
        "universe": ["AAPL"],
        "results": [
            {
                "symbol": "AAPL",
                "price": 100.0,
                "trend": {"bias": "bullish"},
                "liquidity": {"volume": 1, "avgVolume": 1, "volumeRatio": 1.0},
                "earnings": {"nextDate": None, "daysToEarnings": None},
                "options": {
                    "iv": None,
                    "ivRank": None,
                    "ivPercentile": None,
                    "impliedMovePct": None,
                    "suggested": None,
                },
                "markers": {"available": ["symbol", "price"], "missing": []},
            }
        ],
    }
    path = tmp_path / "scan-latest.json"
    path.write_text(json.dumps(scan), encoding="utf-8")
    monkeypatch.setenv("SCANNER_JSON_PATH", str(path))
    monkeypatch.setenv("SCANNER_BASE_URL", "")  # no remote

    env, status, meta = refresh_scan_data(path=path, timeout=0.5)
    assert env is not None
    assert status["ok"] is True
    assert meta["elapsed_ms"] < 2000
    assert meta["mode"] in ("local", "remote_poll")


def test_load_scan_skips_remote_probe_when_local(tmp_path: Path, monkeypatch):
    scan = {
        "schema": "stock-data-scanner.scan/v0.1",
        "asOf": "2026-09-18T21:00:00Z",
        "source": "test",
        "universe": ["MSFT"],
        "results": [
            {
                "symbol": "MSFT",
                "price": 200.0,
                "trend": {"bias": "neutral"},
                "liquidity": {"volume": 1, "avgVolume": 1, "volumeRatio": 1.0},
                "earnings": {"nextDate": None, "daysToEarnings": None},
                "options": {
                    "iv": None,
                    "ivRank": None,
                    "ivPercentile": None,
                    "impliedMovePct": None,
                    "suggested": None,
                },
                "markers": {"available": ["symbol", "price"], "missing": []},
            }
        ],
    }
    path = tmp_path / "scan-latest.json"
    path.write_text(json.dumps(scan), encoding="utf-8")
    monkeypatch.setenv("SCANNER_JSON_PATH", str(path))
    monkeypatch.setenv("SCANNER_BASE_URL", "https://example.invalid")

    env, status = load_scan_envelope(path=path, try_remote=True)
    assert env is not None
    assert "remote probe skipped" in (status.get("remote_note") or "")
