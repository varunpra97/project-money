"""Tests for first-class paper positions: open/close PnL, metrics, greeks EST."""

from __future__ import annotations

from pathlib import Path

from options_seller.execution.paper import PaperExecutor
from options_seller.models.orders import Leg, OrderPlan, Side
from options_seller.portfolio.api import (
    portfolio_greeks_est,
    seed_demo_book,
    summary_metrics,
)
from options_seller.portfolio.payoff import payoff_at_expiration, payoff_series


def _csp_plan(premium: float = 850.0) -> OrderPlan:
    return OrderPlan(
        strategy="cash_secured_put",
        underlying="META",
        legs=[
            Leg(
                symbol="META",
                option_type="put",
                strike=475.0,
                dte=35,
                side=Side.SELL,
                quantity=1,
                limit_price=8.5,
                delta=-0.22,
            )
        ],
        credit_debit="credit",
        net_premium=premium,
        max_profit=premium,
        max_loss=47500.0 - premium,
        capital_required=47500.0,
        is_template=False,
        target_dte=35,
        target_delta=-0.22,
    )


def test_open_creates_first_class_position(tmp_path: Path):
    ex = PaperExecutor(store_path=tmp_path / "pf.json", slippage=0.0)
    ticket = ex.execute(_csp_plan())
    assert ticket.status == "filled_paper"
    opens = ex.list_open()
    assert len(opens) == 1
    pos = opens[0]
    assert pos["id"]
    assert pos["status"] == "open"
    assert pos["underlying"] == "META"
    assert pos["strategy"] == "cash_secured_put"
    assert pos["credit"] == 850.0
    assert pos["capital"] == 47500.0
    assert pos["legs"]
    assert pos["opened_at"]
    assert (tmp_path / "pf.json").exists()


def test_close_position_realized_pnl(tmp_path: Path):
    ex = PaperExecutor(store_path=tmp_path / "pf.json", slippage=0.0)
    ex.execute(_csp_plan(500.0))
    pos = ex.list_open()[0]
    cash_before = ex.portfolio["cash"]

    closed = ex.close_position(pos["id"], price=200.0)
    assert closed["status"] == "closed"
    assert closed["close_price"] == 200.0
    assert closed["realized_pnl"] == 300.0  # 500 credit - 200 buyback
    assert closed["closed_at"]
    assert len(ex.list_open()) == 0
    assert len(ex.list_closed()) == 1

    # Cash: +500 on open, -200 on close
    assert ex.portfolio["cash"] == cash_before - 200.0
    assert ex.portfolio["realized_pnl_lifetime"] == 300.0

    fills = ex.list_fills()
    assert any(f.get("type") == "close" for f in fills)


def test_close_uses_mark_when_price_none(tmp_path: Path):
    ex = PaperExecutor(store_path=tmp_path / "pf.json", slippage=0.0)
    ex.execute(_csp_plan(400.0))
    pos = ex.list_open()[0]
    ex.update_mark(pos["id"], mark=100.0)
    closed = ex.close_position(pos["id"], price=None)
    assert closed["realized_pnl"] == 300.0
    assert closed["close_price"] == 100.0


def test_summary_metrics_and_greeks(tmp_path: Path):
    ex = PaperExecutor(store_path=tmp_path / "pf.json", slippage=0.0)
    seed_demo_book(ex, reset=True)
    m = summary_metrics(ex)
    assert m["open_positions"] >= 4
    assert m["premium_collected"] > 0
    assert m["cash"] > 0
    assert "net_liquidation" in m
    assert "capital_secured" in m

    g = portfolio_greeks_est(ex)
    assert g["estimated"] is True
    assert g["label"] == "EST."
    assert "delta" in g and "theta" in g


def test_payoff_csp_breakeven(tmp_path: Path):
    pos = {
        "credit": 300.0,
        "credit_debit": "credit",
        "legs": [
            {
                "option_type": "put",
                "strike": 100.0,
                "side": "sell",
                "quantity": 1,
            }
        ],
    }
    # At spot 100: intrinsic 0 → pnl = +300
    assert payoff_at_expiration(pos, 100.0) == 300.0
    # At spot 97: intrinsic 3*100=300 → pnl = 0
    assert payoff_at_expiration(pos, 97.0) == 0.0
    # At spot 90: intrinsic 10*100=1000 → pnl = 300-1000 = -700
    assert payoff_at_expiration(pos, 90.0) == -700.0

    series = payoff_series(pos, center=100.0)
    assert len(series["spots"]) == len(series["pnl"])
    assert series["breakevens"]


def test_seed_demo_persists(tmp_path: Path):
    store = tmp_path / "demo.json"
    ex = PaperExecutor(store_path=store)
    seeded = seed_demo_book(ex, reset=True)
    assert len(seeded) == 5
    ex2 = PaperExecutor(store_path=store)
    assert len(ex2.list_open()) >= 5
    assert len(ex2.list_closed()) >= 1
