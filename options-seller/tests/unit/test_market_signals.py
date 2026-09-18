"""Unit tests for stock-data-scanner/market_signals.py pure functions.

No network access: volatility math is checked against synthetic bars and
earnings classification against fixed dates.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

_SIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "stock-data-scanner"
    / "market_signals.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("market_signals_test", _SIG_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["market_signals_test"] = mod
    spec.loader.exec_module(mod)
    return mod


ms = _load()


def _bars(prices, high=None, low=None):
    idx = pd.date_range("2026-01-01", periods=len(prices), freq="B")
    df = pd.DataFrame(
        {
            "Open": prices,
            "High": high if high is not None else [p * 1.01 for p in prices],
            "Low": low if low is not None else [p * 0.99 for p in prices],
            "Close": prices,
            "Volume": [1_000_000] * len(prices),
        },
        index=idx,
    )
    return df


def test_compute_volatility_basic_math():
    prices = [100.0] * 30
    prices[-1] = 110.0  # +10% last session
    prices[-6] = 100.0
    out = ms.compute_volatility(_bars(prices))
    assert out["last"] == 110.0
    assert out["chg_1d_pct"] == pytest.approx(10.0)
    assert out["chg_5d_pct"] == pytest.approx(10.0)
    assert out["max_1d_move_10d_pct"] == pytest.approx(10.0)
    assert out["volatile"] is True
    assert any("single-day" in r for r in out["reasons"])


def test_compute_volatility_calm_market_not_flagged():
    prices = [100.0 + 0.05 * i for i in range(40)]  # gentle drift, tiny moves
    out = ms.compute_volatility(_bars(prices))
    assert out["volatile"] is False
    assert out["reasons"] == []
    assert out["vol_20d_ann_pct"] is not None
    assert out["vol_20d_ann_pct"] < 60.0


def test_compute_volatility_high_realized_vol_flagged():
    import random

    random.seed(7)
    prices = [100.0]
    for _ in range(39):  # ~7% daily noise -> very high annualized vol
        prices.append(prices[-1] * (1 + random.uniform(-0.07, 0.07)))
    out = ms.compute_volatility(_bars(prices))
    assert out["vol_20d_ann_pct"] is not None
    assert out["vol_20d_ann_pct"] > 60.0
    assert out["volatile"] is True


def test_compute_volatility_too_few_bars():
    assert ms.compute_volatility(_bars([100.0] * 5)) == {}
    assert ms.compute_volatility(pd.DataFrame()) == {}


def test_classify_earnings_upcoming_nearby():
    today = date(2026, 9, 18)
    out = ms.classify_earnings([date(2026, 9, 25), date(2026, 6, 20)], today)
    assert out["upcoming"] == "2026-09-25"
    assert out["days_to"] == 7
    assert out["nearby"] is True


def test_classify_earnings_just_reported():
    today = date(2026, 9, 18)
    out = ms.classify_earnings([date(2026, 9, 15)], today)
    assert out["last_reported"] == "2026-09-15"
    assert out["days_since"] == 3
    assert out["nearby"] is True


def test_classify_earnings_far_away_not_nearby():
    today = date(2026, 9, 18)
    out = ms.classify_earnings([date(2026, 12, 1), date(2026, 6, 1)], today)
    assert out["nearby"] is False
    assert out["days_to"] == (date(2026, 12, 1) - today).days


def test_classify_earnings_empty():
    out = ms.classify_earnings([], date(2026, 9, 18))
    assert out == {
        "upcoming": None,
        "days_to": None,
        "last_reported": None,
        "days_since": None,
        "nearby": False,
    }


def test_cache_round_trip(tmp_path):
    payload = {"as_of": "2026-09-18T22:00:00+00:00", "symbols": {"AAPL": {}}, "errors": {}}
    p = tmp_path / "cache.json"
    ms.save_cache(payload, p)
    loaded, fresh = ms.load_cache(p, max_age_hours=10_000)
    assert fresh is True
    assert loaded["symbols"]["AAPL"] == {}
    # stale when TTL is exceeded
    _, fresh2 = ms.load_cache(p, max_age_hours=0)
    assert fresh2 is False
    # missing file
    assert ms.load_cache(tmp_path / "nope.json") == (None, False)
    # broken json
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert ms.load_cache(bad) == (None, False)


def test_norm_cols_multiindex():
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    cols = pd.MultiIndex.from_tuples([("Close", "AAPL"), ("High", "AAPL")])
    df = pd.DataFrame([[1, 2], [3, 4], [5, 6]], index=idx, columns=cols)
    out = ms._norm_cols(df)
    assert list(out.columns) == ["Close", "High"]
