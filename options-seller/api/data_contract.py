"""Content checks shared by server readiness and the cross-platform deployment probe.

No quotes, trades, or history are invented to satisfy readiness. An empty valid
portfolio is different from a missing portfolio store; zero scan matches are
different from zero input bars. This module uses only the Python standard library.
"""
from datetime import datetime, timezone
import math
from urllib.parse import urlparse


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def dated(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (ValueError, TypeError):
        return None


def assess(dataset, payload):
    """Return metadata only; never include private portfolio values in reports."""
    issues = []
    count = None
    stamp = None
    if not isinstance(payload, (dict, list)):
        issues.append("Response is not structured data.")
    elif isinstance(payload, dict) and payload.get("error"):
        issues.append(str(payload["error"])[:180])
    else:
        value = payload if isinstance(payload, dict) else {}
        stamp = value.get("as_of") or value.get("asOf") or value.get("checked_at") or value.get("scan_date")
        kind = dataset.split(":")[0]
        if kind == "summary":
            if not all(finite(value.get(k)) for k in ("account_value", "buying_power", "total_pnl", "open_positions")):
                issues.append("Account summary is missing numeric values.")
        elif kind in ("positions", "activity", "candidates", "celebrity", "earnings", "volatility", "scanners"):
            key = {"celebrity":"moves", "earnings":"rows", "volatility":"rows"}.get(kind, kind)
            rows = payload if kind == "scanners" else value.get(key)
            if not isinstance(rows, list):
                issues.append("Expected a row list.")
            else:
                count = len(rows)
                if kind in ("celebrity", "earnings", "volatility") and not rows:
                    issues.append("The collector returned no universe rows.")
                if kind == "positions" and any(not r.get("id") or not r.get("underlying") for r in rows):
                    issues.append("Position identity or ticker is missing.")
                if kind == "volatility" and not any(finite(r.get("last")) for r in rows):
                    issues.append("No ticker has usable daily price statistics.")
                if kind == "scanners" and any(not r.get("symbols") or not r.get("rule") for r in rows):
                    issues.append("A saved configuration is incomplete.")
            if value.get("fresh") is False:
                issues.append("The last collector result is stale or unavailable.")
        elif kind == "performance":
            if not finite(value.get("pnl")):
                issues.append("Opening period history is missing; P&L remains unavailable.")
            if not isinstance(value.get("curve"), list) or not value["curve"]:
                issues.append("No observed portfolio snapshots exist.")
            count = len(value.get("curve") or [])
        elif kind == "quote":
            bars = value.get("bars")
            if not isinstance(bars, list) or not bars:
                issues.append("No OHLC bars were returned.")
            else:
                count = len(bars)
                if any(not all(finite(b.get(k)) for k in ("t", "o", "h", "l", "c", "v")) or
                       b["h"] < max(b["o"], b["c"], b["l"]) or b["l"] > min(b["o"], b["c"])
                       for b in bars):
                    issues.append("Incomplete or invalid OHLCV bars.")
            if not finite(value.get("price")) or not dated(stamp):
                issues.append("Quote price or source timestamp is missing.")
            if value.get("cache_stale"):
                issues.append("Serving dated cache while the provider refreshes.")
        elif kind == "symbol":
            vol = value.get("volatility")
            if not isinstance(vol, dict) or not finite(vol.get("last")):
                issues.append("Requested ticker price statistics are unavailable.")
            # Earnings may legitimately be absent for ETFs; preserve provider warnings.
        elif kind == "news":
            items = value.get("items")
            count = len(items) if isinstance(items, list) else 0
            if not count:
                issues.append("No publisher headlines are available.")
            elif any(not r.get("title") or not r.get("source") or urlparse(r.get("url", "")).scheme not in ("http", "https") for r in items):
                issues.append("Headlines lack attribution or valid links.")
            if any(s.get("stale") for s in value.get("sources", [])):
                issues.append("One or more publishers could not be refreshed.")
        elif kind == "scan":
            rows = value.get("results", [])
            count = len(rows)
            if value.get("schema") != "stock-data-scanner.scan/v0.1" or not rows:
                issues.append("No valid scanner envelope/results.")
            if not any(finite(r.get("price")) and r["price"] > 0 for r in rows):
                issues.append("The scanner has no usable prices (error stubs do not count).")
            if value.get("feed_status", {}).get("source_kind") == "fallback":
                issues.append("Example fixtures are not production scanner data.")
            if not dated(stamp) or (datetime.now(timezone.utc) - dated(stamp)).total_seconds() > 21600:
                issues.append("Scanner observation is missing or older than six hours.")
        elif kind == "live":
            rows = value.get("quotes", [])
            count = len(rows)
            if not rows or any(not finite(q.get("price")) or not dated(q.get("as_of")) for q in rows):
                issues.append("Live subscriptions have not received dated prices.")
            elif any(q.get("state") == "stale" for q in rows):
                issues.append("Source prices are stale; markets may be closed.")
        elif kind == "history":
            counts = value.get("bars_scanned", {})
            count = sum(counts.values())
            if not counts or any(n < 21 for n in counts.values()):
                issues.append("Historical scan lacks sufficient source bars.")
            if value.get("errors"):
                issues.append("Historical provider failed for one or more symbols.")
        elif kind == "risk":
            if not finite(value.get("aggregate_open_risk")):
                issues.append("Portfolio risk could not be computed.")
        else:
            issues.append("Unknown dataset contract.")
    return {"dataset": dataset, "state": "degraded" if issues else "ready", "issues": issues,
            "count": count, "source_as_of": stamp, "checked_at": datetime.now(timezone.utc).isoformat()}


def probes(symbol="AAPL"):
    paths = {"summary":"/api/portfolio/summary", "positions":"/api/portfolio/positions",
             "activity":"/api/portfolio/activity", "risk":"/api/risk/status", "scan":"/api/scan",
             "news":"/api/news", "celebrity":"/api/insights/celebrity",
             "earnings":"/api/insights/earnings", "volatility":"/api/insights/volatility",
             "candidates":"/api/candidates", "scanners":"/api/history/scanners",
             "symbol":"/api/symbol/"+symbol, "live":"/api/live?symbols="+symbol}
    paths.update({"performance:"+p:"/api/performance?period="+p for p in ("lifetime","week","month","quarter")})
    paths.update({"quote:"+p:"/api/quote/"+symbol+"?range="+p for p in ("1d","5d","1mo","3mo","1y")})
    return paths
