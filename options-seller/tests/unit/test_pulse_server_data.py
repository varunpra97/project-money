"""Verify server data ownership, collection, and content on Windows and macOS."""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from api import main, history, collect_scan, data_status
from api.data_contract import assess, probes
from options_seller.portfolio import scanner_feed


def envelope():
    return {"schema":"stock-data-scanner.scan/v0.1", "asOf":datetime.now(timezone.utc).isoformat(),
            "source":"test-fixture", "universe":["TEST"], "results":[{"symbol":"TEST", "price":100}]}


class ContentTests(unittest.TestCase):
    def test_successful_empty_http_payload_is_not_ready(self):
        for name in probes():
            self.assertEqual(assess(name, {})["state"], "degraded", name)

    def test_no_positions_or_saved_scanners_is_valid_when_lists_exist(self):
        for name, value in (("positions", {"positions":[]}), ("activity", {"activity":[]}), ("scanners", [])):
            self.assertEqual(assess(name, value)["state"], "ready")

    def test_close_only_chart_does_not_pass_candlestick_readiness(self):
        value = {"price":12,"as_of":"2026-01-01T12:00:00Z", "bars":[{"t":123,"c":12}]}
        self.assertEqual(assess("quote:1d", value)["state"], "degraded")
        value["bars"] = [{"t":123,"o":10,"h":13,"l":9,"c":12,"v":100}]
        self.assertEqual(assess("quote:1d", value)["state"], "ready")

    def test_no_matches_requires_actual_input_history(self):
        self.assertEqual(assess("history", {"matches":[],"bars_scanned":{},"errors":[]})["state"], "degraded")
        self.assertEqual(assess("history", {"matches":[],"bars_scanned":{"TEST":250},"errors":[]})["state"], "ready")

    def test_scanner_stubs_examples_and_old_data_fail_readiness(self):
        value = envelope()
        self.assertEqual(assess("scan",value)["state"],"ready")
        for changes in ({"results":[{"symbol":"TEST","price":None}]},
                        {"feed_status":{"source_kind":"fallback"}}, {"asOf":"2000-01-01"}):
            self.assertEqual(assess("scan",{**value,**changes})["state"],"degraded")

    def test_missing_period_baseline_and_publisher_failure_are_explicit(self):
        self.assertEqual(assess("performance:week",{"pnl":None,"curve":[{"ts":"2026-01-01","pnl":1}]})["state"],"degraded")
        news={"items":[{"title":"Test","source":"Fixture","url":"https://example.test/story"}],"sources":[{"stale":True}]}
        self.assertEqual(assess("news",news)["state"],"degraded")

    def test_statistics_need_values_not_only_symbols(self):
        self.assertEqual(assess("volatility",{"rows":[{"symbol":"TEST","last":None}]})["state"],"degraded")
        self.assertEqual(assess("symbol",{"volatility":{"symbol":"TEST","last":100}})["state"],"ready")


class StorageAndCollectorTests(unittest.TestCase):
    def test_all_modules_use_configured_server_directory_from_any_cwd(self):
        with tempfile.TemporaryDirectory(prefix="pulse data ") as folder:
            repo = Path(__file__).resolve().parents[3]
            data = Path(folder)/"persistent store"
            env = dict(os.environ, PULSE_DATA_DIR=str(data), PYTHONPATH=os.pathsep.join([str(repo/"options-seller"),str(repo/"options-seller/src")]))
            code = """
from api import analytics, news, history, assistant, main
from options_seller.portfolio.api import DEFAULT_PAPER_PATH
from options_seller.paths import data_dir
paths=[DEFAULT_PAPER_PATH,analytics.HISTORY,news.CACHE,history.DATA,assistant.STATE,main._signals.CACHE_PATH]
assert all(p.parent==data_dir() for p in paths), paths
assert not DEFAULT_PAPER_PATH.exists(), 'Import must not create portfolio data'
"""
            result = subprocess.run([sys.executable,"-c",code],cwd=folder,env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_and_invalid_portfolio_store_never_report_ready(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(data_status,"data_dir",return_value=Path(folder)):
            catalog=data_status.DataCatalog()
            catalog.record("summary",{"account_value":0,"buying_power":0,"total_pnl":0,"open_positions":0})
            self.assertEqual(catalog.snapshot()["portfolio_store"],"missing")
            self.assertFalse(catalog.snapshot()["ready"])
            path=Path(folder)/"paper_portfolio.json"
            path.write_text("broken")
            self.assertEqual(catalog.snapshot()["portfolio_store"],"invalid")
            path.write_text(json.dumps({"positions":[],"fills":[]}))
            self.assertEqual(catalog.snapshot()["portfolio_store"],"ready")

    def test_api_refuses_example_fallback_and_returns_real_local_envelope(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"scan.json"
            with patch.dict(os.environ,{"SCANNER_JSON_PATH":str(path),"SCANNER_BASE_URL":"","SCANNER_JSON_URL":""}):
                self.assertIsNone(main.load_scan_envelope()[0])
                path.write_text(json.dumps(envelope()))
                main._cache.clear()
                with patch("urllib.request.urlopen",side_effect=OSError("no separate scanner service")):
                    result=main.scan_proxy()
                main._cache.clear()
                self.assertEqual(result["schema"],"stock-data-scanner.scan/v0.1")
                self.assertEqual(result["results"][0]["price"],100)
                self.assertEqual(result["feed_status"]["source_kind"],"local")

    def test_collector_keeps_last_good_file_if_provider_only_returns_errors(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{"SCANNER_JSON_PATH":str(Path(folder)/"scan.json")}):
            path=Path(folder)/"scan.json"
            previous=json.dumps(envelope());path.write_text(previous)
            class FakeScanner:
                @staticmethod
                def build_scan(*args,**kwargs): return {"results":[{"symbol":"TEST","price":None}]}
            with patch.object(collect_scan.importlib.util,"module_from_spec",return_value=FakeScanner), patch.object(collect_scan.importlib.util,"spec_from_file_location") as spec:
                spec.return_value.loader.exec_module.return_value=None
                with self.assertRaises(RuntimeError): collect_scan.collect(["TEST"])
            self.assertEqual(path.read_text(),previous)

    def test_historical_provider_is_called_on_server_with_warmup(self):
        config=history.ScanConfig(symbols=["TEST"],start="2024-01-01",end="2024-02-01",rule="above_sma200")
        bars=pd.DataFrame({"Close":[100.0]*260,"High":[101.0]*260},index=pd.date_range("2023-06-01",periods=260))
        with patch("yfinance.Ticker") as provider:
            provider.return_value.history.return_value=bars
            result=history.run_scan(config)
            self.assertLess(provider.return_value.history.call_args.kwargs["start"],"2024-01-01")
            self.assertEqual(result["bars_scanned"],{"TEST":260})
            self.assertFalse(result["errors"])


if __name__=="__main__": unittest.main()
