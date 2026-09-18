from __future__ import annotations

from options_seller.models.scanner import PortfolioContext, PositionContext
from options_seller.selector import choose_strategy_name, select_and_build


def test_long_shares_selects_covered_call(by_symbol, cfg):
    aapl = by_symbol["AAPL"]
    pos = PositionContext(symbol="AAPL", shares_owned=100, has_shares=True)
    name, reason = choose_strategy_name(aapl, pos, cfg)
    assert name == "covered_call"
    assert "shares" in reason.lower() or "covered" in reason.lower()


def test_bullish_high_iv_csp(by_symbol, cfg):
    # META bullish with ivRank and cash
    meta = by_symbol["META"]
    pos = PositionContext(symbol="META", shares_owned=0, cash_available=60_000)
    name, _ = choose_strategy_name(meta, pos, cfg)
    assert name == "cash_secured_put"


def test_mild_bullish_defined_risk_bull_put(by_symbol, cfg):
    msft = by_symbol["MSFT"]
    pos = PositionContext(symbol="MSFT", prefer_defined_risk=True)
    name, _ = choose_strategy_name(msft, pos, cfg)
    assert name == "bull_put_credit_spread"


def test_mild_bearish_bear_call(by_symbol, cfg):
    nvda = by_symbol["NVDA"]
    pos = PositionContext(symbol="NVDA")
    name, _ = choose_strategy_name(nvda, pos, cfg)
    assert name == "bear_call_credit_spread"


def test_neutral_iron_condor(by_symbol, cfg):
    spy = by_symbol["SPY"]
    pos = PositionContext(symbol="SPY")
    name, _ = choose_strategy_name(spy, pos, cfg)
    assert name == "iron_condor"


def test_earnings_skip(by_symbol, cfg, portfolio):
    tsla = by_symbol["TSLA"]
    sel = select_and_build(tsla, cfg, portfolio)
    assert sel is None


def test_wheel_continuation(by_symbol, cfg):
    # Use AAPL with wheel state assigned
    aapl = by_symbol["AAPL"]
    portfolio = PortfolioContext(
        positions=[PositionContext(symbol="AAPL", shares_owned=100, wheel_state="assigned")]
    )
    sel = select_and_build(aapl, cfg, portfolio)
    assert sel is not None
    assert sel.strategy_name == "wheel"
