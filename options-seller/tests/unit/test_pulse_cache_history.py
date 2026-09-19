"""Regression coverage for shared quote refreshes and causal historical scans."""
import asyncio
from datetime import date
import tempfile
import threading
import time
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
from pydantic import ValidationError

from api.cache import AsyncCache
from api import history, main


class CacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.cache = AsyncCache()

    async def asyncTearDown(self):
        await self.cache.close()

    async def test_cold_requests_share_one_provider_fetch(self):
        calls = []
        def fetch():
            calls.append(1)
            time.sleep(.03)
            return {"price": 123}
        results = await asyncio.gather(*(self.cache.get("TEST", fetch) for _ in range(12)))
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(r["price"] == 123 and not r["cache_stale"] for r in results))

    async def test_stale_reply_does_not_wait_for_provider(self):
        await self.cache.get("TEST", lambda: {"price": 100}, ttl=-1)
        release = threading.Event()
        def fetch():
            release.wait(2)
            return {"price": 101}
        try:
            result = await asyncio.wait_for(self.cache.get("TEST", fetch), .25)
            self.assertEqual(result["price"], 100)
            self.assertTrue(result["cache_stale"])
        finally:
            release.set()
        await asyncio.gather(*list(self.cache.inflight.values()))
        result = await self.cache.get("TEST", fetch)
        self.assertEqual(result["price"], 101)
        self.assertFalse(result["cache_stale"])

    async def test_failed_refresh_preserves_dated_value_and_does_not_cache_error(self):
        await self.cache.get("TEST", lambda: {"price": 100}, ttl=-1)
        result = await self.cache.get("TEST", lambda: {"error": "provider unavailable"}, force=True)
        self.assertEqual(result["price"], 100)
        self.assertTrue(result["cache_stale"])
        self.assertIn("provider unavailable", result["cache_warning"])
        with self.assertRaises(RuntimeError):
            await self.cache.get("NEW", lambda: {"error": "unavailable"})
        self.assertNotIn("NEW", self.cache.values)

    async def test_active_history_refreshes_without_a_client_request(self):
        await self.cache.get("TEST", lambda: {"price": 200}, ttl=-1)
        self.cache.fetches["TEST"] = (lambda: {"price": 201}, 20, time.monotonic())
        self.cache.worker = asyncio.create_task(self.cache.maintain())
        for _ in range(100):
            if self.cache.values["TEST"][2]["price"] == 201:
                break
            await asyncio.sleep(.01)
        self.assertEqual(self.cache.values["TEST"][2]["price"], 201)


class HistoricalTests(unittest.TestCase):
    def config(self, **values):
        return history.ScanConfig(**{"symbols": ["TEST"], "start": date(2024, 1, 1),
                                     "end": date(2025, 1, 1), **values})

    def frame(self):
        closes = [100 + (i % 40) - 20 for i in range(300)]
        return pd.DataFrame({"Close": closes, "High": [p + 1 for p in closes]},
                            index=pd.date_range("2023-06-01", periods=300))

    def test_future_bars_cannot_change_past_signals(self):
        frame = self.frame()
        for rule in history.RULES:
            config = self.config(rule=rule)
            cutoff = frame.index[250].date().isoformat()
            before, _ = history.evaluate(frame.iloc[:251], config, "TEST")
            after, _ = history.evaluate(frame, config, "TEST")
            self.assertEqual(before, [r for r in after if r["date"] <= cutoff], rule)
            self.assertTrue(all(r["date"] >= config.start.isoformat() for r in after))

    def test_breakout_uses_prior_highs(self):
        frame = pd.DataFrame({"Close": [10] * 20 + [12], "High": [11] * 20 + [13]},
                             index=pd.date_range("2024-01-01", periods=21))
        rows, _ = history.evaluate(frame, self.config(rule="breakout20"), "TEST")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["indicator"], 11)

    def test_validation_and_symbol_normalization(self):
        self.assertEqual(self.config(symbols=[" aapl ", "AAPL"]).symbols, ["AAPL"])
        for values in ({"symbols": ["../secret"]}, {"symbols": []},
                       {"start": date(2025, 2, 1)}, {"end": date(2099, 1, 1)}):
            with self.assertRaises(ValidationError):
                self.config(**values)

    def test_saved_configuration_round_trip(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(history, "DATA", Path(folder)/"scanners.json"):
            saved = history.save(self.config())
            self.assertEqual(history.saved(), [saved])
            self.assertEqual(saved["start"], "2024-01-01")


class RouteContractTests(unittest.TestCase):
    def test_mobile_routes_survive_backend_merges(self):
        paths = set(main.app.inner.openapi()["paths"])
        required = {"/api/health", "/api/risk/status", "/api/scan", "/api/quote/{symbol}",
                    "/api/symbol/{symbol}", "/api/performance", "/api/news", "/api/live/events",
                    "/api/portfolio/positions", "/api/assistant/status", "/api/history/run"}
        self.assertFalse(required - paths, f"Missing routes: {required - paths}")

    def test_position_metrics_keep_unknown_daily_return_unavailable(self):
        main._cache.clear()
        position = {"id": "test", "underlying": "TEST", "status": "open", "legs": [],
                    "credit": 200, "mark": 80, "unrealized_pnl": 120, "credit_debit": "credit",
                    "expiry": "2026-10-16"}
        with patch.object(main, "load_executor") as executor:
            executor.return_value.list_open.return_value = [position]
            row = main.portfolio_positions()["positions"][0]
        main._cache.clear()
        self.assertIsNone(row["day_pnl"])
        self.assertEqual(row["return_pct"], 60)
        self.assertEqual(row["equity"], -80)
        self.assertEqual(row["expiry"], "2026-10-16")
        self.assertEqual(row["opening_value"], 200)
        self.assertEqual(row["close_value"], 80)

    def test_debit_position_values_and_shared_leg_expiry(self):
        main._cache.clear()
        position = {"id":"debit", "status":"open", "underlying":"TEST", "credit":-200,
                    "mark":240, "unrealized_pnl":40, "credit_debit":"debit",
                    "legs":[{"expiry":"2026-10-16", "strike":100, "quantity":1, "side":"buy"}]}
        with patch.object(main, "load_executor") as executor:
            executor.return_value.list_open.return_value=[position]
            row=main.portfolio_positions()["positions"][0]
        main._cache.clear()
        self.assertEqual((row["opening_value"],row["close_value"],row["equity"]),(200,240,240))
        self.assertEqual(row["expiry"],"2026-10-16")

    def test_scanner_expiration_survives_order_and_position_storage(self):
        from options_seller.models.scanner import SuggestedLeg
        from options_seller.models.orders import OrderPlan
        from options_seller.strategies.base import suggested_to_leg
        from options_seller.execution.paper import PaperExecutor
        leg=suggested_to_leg("TEST",SuggestedLeg(strike=100,dte=27,expiration="2026-10-16",right="put",premium=2))
        plan=OrderPlan(underlying="TEST",strategy="cash_secured_put",legs=[leg],net_premium=200,capital_required=10000,max_loss=9800)
        with tempfile.TemporaryDirectory() as folder:
            executor=PaperExecutor(store_path=Path(folder)/"paper.json")
            executor.execute(plan)
            position=executor.list_open()[0]
            self.assertEqual(position["legs"][0]["expiry"],"2026-10-16")
            executor.update_mark(position["id"],mark=80)
            reloaded=PaperExecutor(store_path=Path(folder)/"paper.json").list_open()[0]
            self.assertTrue(reloaded["marked_at"])


class StreamRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_closed_provider_socket_is_discarded_for_reconnect(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from api.live import LivePrices
        feed=LivePrices()
        closed=SimpleNamespace(_ws=SimpleNamespace(close_code=1006),close=AsyncMock())
        feed.ws=closed
        feed.wanted["TEST"]=time.time()
        feed.polled["TEST"]=time.time()
        feed.task=asyncio.create_task(feed.run())
        try:
            for _ in range(50):
                if feed.ws is None: break
                await asyncio.sleep(.01)
            self.assertIsNone(feed.ws)
            closed.close.assert_awaited_once()
            self.assertFalse(feed.subscribed)
        finally:
            await feed.stop()


if __name__ == "__main__":
    unittest.main()
