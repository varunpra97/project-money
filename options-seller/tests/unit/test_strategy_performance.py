"""Tests for strategy/ticker performance helpers and celebrity priority."""

from __future__ import annotations

from pathlib import Path

from options_seller.execution.paper import PaperExecutor
from options_seller.portfolio.api import (
    days_held,
    pct_of_max_profit,
    seed_demo_book,
    strategies_in_play,
    strategy_performance,
    ticker_performance,
)
from options_seller.portfolio.celebrity_priority import (
    caution_for,
    celebrity_overlay,
    is_priority,
    priority_badge,
    rollup_ticker,
)


def test_pct_of_max_profit():
    assert pct_of_max_profit(50, 100) == 50.0
    assert pct_of_max_profit(0, 100) == 0.0
    assert pct_of_max_profit(10, 0) is None
    assert pct_of_max_profit(10, None) is None
    assert pct_of_max_profit(None, 100) is None


def test_days_held_closed():
    d = days_held("2026-09-01T00:00:00+00:00", "2026-09-11T00:00:00+00:00")
    assert d == 10.0


def test_strategy_performance_demo(tmp_path: Path):
    ex = PaperExecutor(store_path=tmp_path / "pf.json", slippage=0.0)
    seed_demo_book(ex, reset=True)
    rows = strategy_performance(ex)
    assert rows
    by = {r["strategy"]: r for r in rows}
    assert "cash_secured_put" in by
    csp = by["cash_secured_put"]
    # demo: 1 open AAPL CSP + 1 closed META CSP
    assert csp["open_count"] >= 1
    assert csp["closed_count"] >= 1
    assert csp["realized"] > 0  # META closed winner
    assert csp["win_rate"] == 100.0
    assert csp["avg_win"] is not None
    assert csp["premium_collected"] > 0
    assert "unrealized" in csp

    in_play = strategies_in_play(ex)
    assert all(r["open_count"] >= 1 for r in in_play)
    assert len(in_play) >= 4


def test_ticker_performance_demo(tmp_path: Path):
    ex = PaperExecutor(store_path=tmp_path / "pf.json", slippage=0.0)
    seed_demo_book(ex, reset=True)
    rows = ticker_performance(ex)
    by = {r["ticker"]: r for r in rows}
    assert "META" in by
    assert by["META"]["closed_count"] == 1
    assert by["META"]["realized"] > 0
    assert "AAPL" in by
    assert by["AAPL"]["open_count"] == 1


def test_win_loss_avg(tmp_path: Path):
    ex = PaperExecutor(store_path=tmp_path / "pf.json", slippage=0.0)
    # Two closed CSPs: win + loss
    w = ex.open_demo_position(
        underlying="AAA",
        strategy="cash_secured_put",
        legs=[{"symbol": "AAA", "option_type": "put", "strike": 50.0, "dte": 10, "side": "sell", "quantity": 1}],
        credit=200.0,
        capital=5000.0,
        max_profit=200.0,
        max_loss=4800.0,
        dte=10,
        mark_fraction=0.5,
    )
    ex.close_position(w["id"], price=50.0)  # +150
    l = ex.open_demo_position(
        underlying="BBB",
        strategy="cash_secured_put",
        legs=[{"symbol": "BBB", "option_type": "put", "strike": 40.0, "dte": 10, "side": "sell", "quantity": 1}],
        credit=100.0,
        capital=4000.0,
        max_profit=100.0,
        max_loss=3900.0,
        dte=10,
        mark_fraction=0.5,
    )
    ex.close_position(l["id"], price=180.0)  # -80
    rows = strategy_performance(ex)
    csp = next(r for r in rows if r["strategy"] == "cash_secured_put")
    assert csp["closed_count"] == 2
    assert csp["win_rate"] == 50.0
    assert csp["avg_win"] == 150.0
    assert csp["avg_loss"] == -80.0
    assert csp["realized"] == 70.0


def test_celebrity_priority_overlay():
    assert is_priority("amzn")
    assert is_priority("SPCX")
    assert not is_priority("AAPL")
    assert priority_badge("META") == "⭐ Priority"
    assert priority_badge("FDXF") == "◇ Mention"
    assert priority_badge("AAPL") is None
    assert rollup_ticker("GOOG") == "GOOGL"
    assert rollup_ticker("GOOGL") == "GOOGL"
    assert "lockup" in (caution_for("SPCX") or "").lower() or "listing" in (caution_for("SPCX") or "").lower()
    ov = celebrity_overlay("INTC")
    assert ov["is_priority"]
    assert ov["pelosi_linked"]
    assert "share counts" in (ov["caution"] or "").lower()
    ov2 = celebrity_overlay("VST")
    assert ov2["prefer_volume_cols"]


def test_dual_class_ticker_rollup(tmp_path: Path):
    ex = PaperExecutor(store_path=tmp_path / "pf.json", slippage=0.0)
    ex.open_demo_position(
        underlying="GOOG",
        strategy="covered_call",
        legs=[{"symbol": "GOOG", "option_type": "call", "strike": 180.0, "dte": 20, "side": "sell", "quantity": 1}],
        credit=100.0,
        capital=17000.0,
        max_profit=100.0,
        dte=20,
        mark_fraction=0.5,
    )
    ex.open_demo_position(
        underlying="GOOGL",
        strategy="covered_call",
        legs=[{"symbol": "GOOGL", "option_type": "call", "strike": 180.0, "dte": 20, "side": "sell", "quantity": 1}],
        credit=120.0,
        capital=17000.0,
        max_profit=120.0,
        dte=20,
        mark_fraction=0.5,
    )
    rows = ticker_performance(ex)
    by = {r["ticker"]: r for r in rows}
    assert "GOOGL" in by
    assert "GOOG" not in by  # normalized away
    assert by["GOOGL"]["open_count"] == 2
    assert by["GOOGL"]["premium_collected"] == 220.0
