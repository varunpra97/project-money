"""Unit tests for hard $50k portfolio risk limits (paper only)."""

from __future__ import annotations

from pathlib import Path

from options_seller.execution.paper import PaperExecutor
from options_seller.models.orders import Leg, OrderPlan, Side
from options_seller.risk.enforce import enforce_hard_limits
from options_seller.risk.limits import (
    RiskLimits,
    aggregate_open_risk,
    can_open,
    evaluate_book,
    headroom,
    pick_trim_targets,
    position_risk,
)


def _pos(
    *,
    pid: str,
    max_loss=None,
    capital=0.0,
    status: str = "open",
    opened_at: str = "2026-01-01T00:00:00+00:00",
    underlying: str = "TEST",
) -> dict:
    return {
        "id": pid,
        "underlying": underlying,
        "strategy": "cash_secured_put",
        "max_loss": max_loss,
        "capital": capital,
        "status": status,
        "opened_at": opened_at,
        "credit": 100.0,
        "credit_debit": "credit",
        "mark": 50.0,
        "legs": [],
    }


def test_empty_book():
    limits = RiskLimits()
    assert aggregate_open_risk([]) == 0.0
    assert headroom([], limits) == 50_000.0
    ok, reason = can_open([], 10_000.0, limits)
    assert ok is True
    assert "ok" in reason
    book = evaluate_book([], limits)
    assert book["status"] == "ok"
    assert book["aggregate_open_risk"] == 0.0
    assert book["headroom"] == 50_000.0
    assert pick_trim_targets([], limits) == []


def test_under_cap():
    positions = [
        _pos(pid="a", max_loss=20_000.0, capital=21_000.0),
        _pos(pid="b", max_loss=15_000.0, capital=16_000.0),
    ]
    limits = RiskLimits()
    assert aggregate_open_risk(positions) == 35_000.0
    assert headroom(positions, limits) == 15_000.0
    ok, _ = can_open(positions, 10_000.0, limits)
    assert ok is True
    book = evaluate_book(positions, limits)
    assert book["status"] == "ok"
    assert book["soft_warn"] is False


def test_soft_warn_no_auto_trim():
    positions = [_pos(pid="a", max_loss=42_000.0, capital=42_000.0)]
    book = evaluate_book(positions, RiskLimits())
    assert book["status"] == "soft_warn"
    assert book["soft_warn"] is True
    assert book["hard_breach"] is False
    assert pick_trim_targets(positions, RiskLimits()) == []


def test_reject_over_cap():
    positions = [_pos(pid="a", max_loss=45_000.0, capital=45_000.0)]
    ok, reason = can_open(positions, 10_000.0, RiskLimits())
    assert ok is False
    assert "risk_rejected" in reason
    assert "headroom" in reason


def test_max_loss_vs_capital_fallback():
    with_ml = _pos(pid="1", max_loss=5_000.0, capital=50_000.0)
    assert position_risk(with_ml) == 5_000.0
    no_ml = _pos(pid="2", max_loss=None, capital=13_000.0)
    assert position_risk(no_ml) == 13_000.0
    closed = _pos(pid="3", max_loss=99_000.0, capital=99_000.0, status="closed")
    assert aggregate_open_risk([with_ml, no_ml, closed]) == 18_000.0


def test_trim_ordering():
    """Largest risk first; tie-break largest capital, then oldest."""
    positions = [
        _pos(
            pid="old_small",
            max_loss=20_000.0,
            capital=20_000.0,
            opened_at="2026-01-01T00:00:00+00:00",
        ),
        _pos(
            pid="newest_big",
            max_loss=30_000.0,
            capital=30_000.0,
            opened_at="2026-03-01T00:00:00+00:00",
        ),
        _pos(
            pid="mid_tie_high_cap",
            max_loss=25_000.0,
            capital=40_000.0,
            opened_at="2026-02-01T00:00:00+00:00",
        ),
        _pos(
            pid="mid_tie_low_cap",
            max_loss=25_000.0,
            capital=10_000.0,
            opened_at="2026-02-01T00:00:00+00:00",
        ),
    ]
    # Aggregate = 20+30+25+25 = 100k; need to trim until <= 50k
    targets = pick_trim_targets(positions, RiskLimits(max_portfolio_risk_usd=50_000))
    # Order: newest_big (30k), mid_tie_high_cap (25k, higher capital), ...
    assert targets[0] == "newest_big"
    assert targets[1] == "mid_tie_high_cap"
    # After freeing 30+25=55, remaining = 100-55=45 <= 50 → stop
    assert targets == ["newest_big", "mid_tie_high_cap"]


def test_trim_tie_oldest():
    """Same risk and capital → close oldest first."""
    positions = [
        _pos(
            pid="newer",
            max_loss=40_000.0,
            capital=40_000.0,
            opened_at="2026-06-01T00:00:00+00:00",
        ),
        _pos(
            pid="older",
            max_loss=40_000.0,
            capital=40_000.0,
            opened_at="2026-01-01T00:00:00+00:00",
        ),
    ]
    targets = pick_trim_targets(positions, RiskLimits(max_portfolio_risk_usd=50_000))
    assert targets[0] == "older"
    assert len(targets) == 1  # free 40k → remaining 40k <= 50k


def test_executor_rejects_over_cap(tmp_path: Path):
    store = tmp_path / "pf.json"
    limits = RiskLimits(max_portfolio_risk_usd=50_000)
    ex = PaperExecutor(store_path=store, slippage=0.0, risk_limits=limits)
    plan_big = OrderPlan(
        strategy="cash_secured_put",
        underlying="META",
        legs=[
            Leg(
                symbol="META",
                option_type="put",
                strike=500.0,
                dte=30,
                side=Side.SELL,
                quantity=1,
            )
        ],
        credit_debit="credit",
        net_premium=400.0,
        max_profit=400.0,
        max_loss=49_600.0,
        capital_required=50_000.0,
        is_template=False,
    )
    t1 = ex.execute(plan_big)
    assert t1.status == "filled_paper"
    plan2 = OrderPlan(
        strategy="bull_put_credit_spread",
        underlying="MSFT",
        legs=[
            Leg(
                symbol="MSFT",
                option_type="put",
                strike=400.0,
                dte=28,
                side=Side.SELL,
                quantity=1,
            ),
            Leg(
                symbol="MSFT",
                option_type="put",
                strike=390.0,
                dte=28,
                side=Side.BUY,
                quantity=1,
            ),
        ],
        credit_debit="credit",
        net_premium=150.0,
        max_profit=150.0,
        max_loss=850.0,
        capital_required=1_000.0,
        is_template=False,
    )
    t2 = ex.execute(plan2)
    assert t2.status == "risk_rejected"
    assert t2.fill_price is None
    assert "risk_rejected" in (t2.plan.notes or "")
    assert aggregate_open_risk(ex.portfolio["positions"]) == 49_600.0
    assert any(f.get("type") == "risk_rejected" for f in ex.portfolio["fills"])


def test_enforce_trims_highest_risk(tmp_path: Path):
    store = tmp_path / "pf.json"
    limits = RiskLimits(max_portfolio_risk_usd=50_000)
    ex = PaperExecutor(store_path=store, slippage=0.0, risk_limits=limits)
    # Seed via open_demo_position (bypasses gate) to create over-cap book
    ex.open_demo_position(
        underlying="AAPL",
        strategy="cash_secured_put",
        legs=[{"symbol": "AAPL", "option_type": "put", "strike": 200.0, "dte": 30, "side": "sell", "quantity": 1}],
        credit=200.0,
        capital=20_000.0,
        max_loss=19_800.0,
        dte=30,
    )
    ex.open_demo_position(
        underlying="META",
        strategy="cash_secured_put",
        legs=[{"symbol": "META", "option_type": "put", "strike": 400.0, "dte": 30, "side": "sell", "quantity": 1}],
        credit=300.0,
        capital=40_000.0,
        max_loss=39_700.0,
        dte=30,
    )
    assert aggregate_open_risk(ex.portfolio["positions"]) > 50_000
    result = enforce_hard_limits(ex, limits)
    assert result["trimmed"] is True
    assert result["after"]["aggregate_open_risk"] <= 50_000
    assert result["after"]["hard_breach"] is False
    # META (higher risk) should have been closed
    meta = next(p for p in ex.portfolio["positions"] if p["underlying"] == "META")
    assert meta["status"] == "closed"
    assert any(e.get("type") == "risk_trim" for e in ex.portfolio.get("risk_events", []))


def test_demo_seed_under_cap(tmp_path: Path):
    from options_seller.portfolio.api import seed_demo_book

    store = tmp_path / "pf.json"
    ex = PaperExecutor(store_path=store)
    seed_demo_book(ex, reset=True)
    agg = aggregate_open_risk(ex.portfolio["positions"])
    assert agg <= 50_000.0, f"demo seed aggregate risk {agg} exceeds 50k"
