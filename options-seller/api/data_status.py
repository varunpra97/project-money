"""Cheap readiness metadata; collectors do expensive work away from request handlers."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from options_seller.paths import data_dir
try:
    from .data_contract import assess
except ImportError:
    from data_contract import assess

class DataCatalog:
    expected = ("summary", "positions", "activity", "risk", "news", "celebrity",
                "earnings", "volatility", "candidates", "scan", "performance:lifetime",
                "performance:week", "performance:month", "performance:quarter")
    def __init__(self):
        self.checks = {}

    def record(self, name, payload):
        self.checks[name] = assess(name, payload)

    async def collect(self, providers):
        # Groups are sequential here: earnings/volatility share one underlying cache.
        for name, fetch in providers.items():
            try:
                payload = await asyncio.to_thread(fetch)
                if hasattr(payload, "body"):
                    payload = json.loads(payload.body)
                self.record(name, payload)
            except Exception as error:
                self.record(name, {"error": str(error)[:180]})

    def snapshot(self):
        store = data_dir()/"paper_portfolio.json"
        try:
            raw = json.loads(store.read_text())
            valid = isinstance(raw, dict) and isinstance(raw.get("positions"), list) and isinstance(raw.get("fills"), list)
            portfolio = "ready" if valid else "invalid"
        except FileNotFoundError:
            portfolio = "missing"
        except (OSError, ValueError):
            portfolio = "invalid"
        checks = [self.checks.get(name, {"dataset":name, "state":"pending", "issues":["Collector has not finished yet."]}) for name in self.expected]
        ready = bool(checks) and portfolio == "ready" and all(c["state"] == "ready" for c in checks)
        return {"ready": ready, "portfolio_store": portfolio, "checks": checks,
                "note": "Missing portfolio/history must be provisioned on this server. No demo fallback. Quotes and custom historical scans are verified by api.check_data.",
                "checked_at": datetime.now(timezone.utc).isoformat()}

catalog = DataCatalog()
