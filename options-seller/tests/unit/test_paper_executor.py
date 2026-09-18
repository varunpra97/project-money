from __future__ import annotations

from pathlib import Path

from options_seller.execution.broker import StubBrokerAdapter, plan_to_ticket
from options_seller.execution.paper import PaperExecutor
from options_seller.models.orders import Leg, OrderPlan, Side
from options_seller.strategies.cash_secured_put import CashSecuredPut


def _sample_plan() -> OrderPlan:
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
            )
        ],
        credit_debit="credit",
        net_premium=850.0,
        max_profit=850.0,
        max_loss=46650.0,
        capital_required=47500.0,
        is_template=False,
    )


def test_paper_fill_at_mid_with_slippage(tmp_path: Path):
    store = tmp_path / "pf.json"
    ex = PaperExecutor(store_path=store, slippage=0.02)
    ticket = ex.execute(_sample_plan())
    assert ticket.status == "filled_paper"
    assert ticket.paper is True
    assert ticket.fill_price is not None
    assert ticket.fill_price == 850.0 * 0.98
    assert store.exists()
    assert len(ex.portfolio["fills"]) == 1


def test_template_not_filled(tmp_path: Path, minimal_scan, cfg):
    res = CashSecuredPut(cfg).build(minimal_scan)
    assert res is not None
    ex = PaperExecutor(store_path=tmp_path / "pf.json")
    ticket = ex.execute(res.plan)
    assert ticket.status == "template_only"
    assert ticket.fill_price is None


def test_sqlite_persist(tmp_path: Path):
    store = tmp_path / "pf.json"
    ex = PaperExecutor(store_path=store, use_sqlite=True, slippage=0.0)
    ex.execute(_sample_plan())
    ex2 = PaperExecutor(store_path=store, use_sqlite=True)
    assert len(ex2.portfolio["fills"]) == 1


def test_stub_broker_unimplemented():
    stub = StubBrokerAdapter()
    ticket = plan_to_ticket(_sample_plan())
    try:
        stub.place_order(ticket)
        assert False, "should raise"
    except NotImplementedError as e:
        assert "unimplemented" in str(e).lower() or "not implemented" in str(e).lower()
