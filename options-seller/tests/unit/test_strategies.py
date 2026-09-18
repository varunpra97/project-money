from __future__ import annotations

import json
from pathlib import Path

from options_seller.models.scanner import PortfolioContext, PositionContext, ScanEnvelope
from options_seller.strategies.bear_call_credit_spread import BearCallCreditSpread
from options_seller.strategies.bull_put_credit_spread import BullPutCreditSpread
from options_seller.strategies.cash_secured_put import CashSecuredPut
from options_seller.strategies.covered_call import CoveredCall
from options_seller.strategies.iron_condor import IronCondor
from options_seller.strategies.wheel import WheelStrategy

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_csp_template_when_options_null(minimal_scan, cfg):
    minimal_scan.trend.bias = "bullish"  # type: ignore[attr-defined]
    res = CashSecuredPut(cfg).build(minimal_scan)
    assert res is not None
    assert res.plan.is_template is True
    assert res.plan.target_dte is not None
    assert res.plan.target_delta is not None
    assert res.plan.net_premium is None  # never invent


def test_csp_from_suggested(by_symbol, cfg):
    meta = by_symbol["META"]
    res = CashSecuredPut(cfg).build(meta)
    assert res is not None
    assert res.used_suggested is True
    assert res.plan.is_template is False
    assert res.plan.net_premium is not None
    assert res.plan.max_profit == res.plan.net_premium
    assert res.plan.capital_required is not None


def test_covered_call_builder(by_symbol, cfg):
    aapl = by_symbol["AAPL"]
    pos = PositionContext(symbol="AAPL", shares_owned=100)
    res = CoveredCall(cfg).build(aapl, pos)
    assert res is not None
    assert res.plan.strategy == "covered_call"
    assert res.plan.legs[0].option_type == "call"


def test_bull_put_template_and_metrics(by_symbol, cfg):
    msft = by_symbol["MSFT"]
    res = BullPutCreditSpread(cfg).build(msft)
    assert res is not None
    assert len(res.plan.legs) == 2
    assert res.plan.legs[0].side.value == "sell"
    assert res.plan.legs[1].side.value == "buy"
    # template path (no suggested) still has capital from width heuristic
    assert res.plan.capital_required is not None


def test_bull_put_from_suggested(by_symbol, cfg):
    meta = by_symbol["META"]
    res = BullPutCreditSpread(cfg).build(meta)
    assert res is not None
    assert res.used_suggested is True
    assert res.plan.max_loss is not None
    assert res.plan.max_profit is not None
    # max_loss = width - credit (per contract dollars already)
    assert res.plan.max_loss > 0


def test_bear_call(by_symbol, cfg):
    nvda = by_symbol["NVDA"]
    res = BearCallCreditSpread(cfg).build(nvda)
    assert res is not None
    assert res.plan.strategy == "bear_call_credit_spread"
    assert len(res.plan.legs) == 2


def test_iron_condor_from_fixture(cfg):
    data = json.loads((FIXTURES / "iron_condor_scan.json").read_text())
    scan = ScanEnvelope.load(data).results[0]
    res = IronCondor(cfg).build(scan)
    assert res is not None
    assert res.used_suggested is True
    assert len(res.plan.legs) == 4
    assert res.plan.net_premium is not None


def test_iron_condor_template(minimal_scan, cfg):
    res = IronCondor(cfg).build(minimal_scan)
    assert res is not None
    assert res.plan.is_template is True
    assert len(res.plan.legs) == 4
    assert res.plan.target_delta is not None


def test_wheel_csp_phase(by_symbol, cfg):
    meta = by_symbol["META"]
    pos = PositionContext(symbol="META", shares_owned=0, wheel_state="idle")
    res = WheelStrategy(cfg).build(meta, pos)
    assert res is not None
    assert res.plan.metadata["inner_strategy"] == "cash_secured_put"


def test_wheel_cc_phase(by_symbol, cfg):
    aapl = by_symbol["AAPL"]
    pos = PositionContext(symbol="AAPL", shares_owned=100, wheel_state="assigned")
    res = WheelStrategy(cfg).build(aapl, pos)
    assert res is not None
    assert res.plan.metadata["inner_strategy"] == "covered_call"
