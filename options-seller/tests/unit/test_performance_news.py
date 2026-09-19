"""Validate period math, missing-history behavior, resets, and RSS trust boundaries."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from api.analytics import performance
from api.news import parse_feed, news_feed

NOW = datetime(2026, 9, 19, tzinfo=timezone.utc)

class Book:
    def __init__(self):
        self.portfolio = {"cash": 1000, "starting_cash": 1000, "realized_pnl_lifetime": 75,
            "positions": [{"id": "a", "opened_at": (NOW-timedelta(days=40)).isoformat()}],
            "fills": []}
        self.closed = [
            {"strategy": "spread", "closed_at": (NOW-timedelta(days=2)).isoformat(), "realized_pnl": 100},
            {"strategy": "spread", "closed_at": (NOW-timedelta(days=10)).isoformat(), "realized_pnl": -25}]
    def list_open(self): return [{"status": "open", "unrealized_pnl": 20}]
    def list_closed(self): return self.closed

class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/"history.json"
        self.book = Book()
    def run_stats(self, period="lifetime", now=NOW):
        return performance(period, self.book, now, self.path)
    def test_missing_baseline_is_not_fabricated(self):
        r = self.run_stats("week")
        self.assertIsNone(r["pnl"])
        self.assertEqual(r["realized"], 100)
        self.assertEqual(r["closed_trades"], 1)
        self.assertEqual(r["win_rate"], 100)
    def test_lifetime_and_month_different_metrics(self):
        life = self.run_stats()
        self.assertEqual(life["pnl"], 95)
        self.assertEqual(life["win_rate"], 50)
        self.assertEqual(life["profit_factor"], 4)
        self.assertEqual(self.run_stats("month")["realized"], 75)
    def test_period_change_uses_observed_baseline(self):
        self.run_stats(now=NOW-timedelta(days=7))
        self.book.portfolio["realized_pnl_lifetime"] += 15
        r = self.run_stats("week")
        self.assertEqual(r["pnl"], 15)
        self.assertEqual(r["curve"][0]["pnl"], 0)
    def test_old_baseline_does_not_claim_full_coverage(self):
        self.run_stats(now=NOW-timedelta(days=10))
        self.assertIsNone(self.run_stats("week")["pnl"])
    def test_snapshot_not_rewritten_by_poll(self):
        self.run_stats()
        self.run_stats(now=NOW+timedelta(seconds=10))
        self.assertEqual(json.loads(self.path.read_text())["samples"][0]["ts"], NOW.isoformat())
    def test_reset_clears_previous_history(self):
        self.run_stats(now=NOW-timedelta(days=7))
        self.book.portfolio["positions"] = []
        self.assertIsNone(self.run_stats("week")["pnl"])
        self.assertEqual(len(json.loads(self.path.read_text())["samples"]), 1)
    def test_empty_closes_and_carry_balance(self):
        self.book.closed = []
        r = self.run_stats()
        self.assertIsNone(r["win_rate"])
        self.assertIsNone(r["profit_factor"])
        self.assertTrue(any("carried balance" in n for n in r["notes"]))
    def test_future_and_missing_close_dates_excluded(self):
        self.book.closed.extend([{"closed_at": (NOW+timedelta(days=1)).isoformat(), "realized_pnl": 999}, {"realized_pnl": 999}])
        self.assertEqual(self.run_stats("week")["realized"], 100)

class NewsTests(unittest.TestCase):
    def test_safe_links_and_dates(self):
        body = b'<rss><channel><item><title>Options &amp; markets</title><link>https://example.com/a</link><pubDate>Fri, 18 Sep 2026 12:00:00 GMT</pubDate></item><item><title>Unsafe</title><link>javascript:alert(1)</link></item></channel></rss>'
        rows = parse_feed(body, "Example", "Options")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Options & markets")
        self.assertEqual(rows[0]["published"], "2026-09-18T12:00:00+00:00")
    def test_failure_retains_dated_cache(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"news.json"
            path.write_text(json.dumps({"checked":0,"sources":{"Cboe Insights":{"items":[{"id":"x","url":"https://example.com/a","title":"Options news","source":"Cboe Insights","category":"Options","published":"2026-09-18T12:00:00+00:00"}],"fetched":"old","stale":False}}}))
            with patch("api.news.CACHE",path), patch("api.news.fetch_source",side_effect=OSError("offline")):
                r = news_feed()
            self.assertEqual(len(r["items"]),1)
            self.assertTrue(r["items"][0]["stale"])
            self.assertEqual(len(r["ideas"]),4)

if __name__ == "__main__": unittest.main()
