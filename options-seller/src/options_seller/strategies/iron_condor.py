"""Iron condor strategy."""

from __future__ import annotations

from typing import Optional

from options_seller.models.orders import OrderPlan, Side
from options_seller.models.scanner import (
    OptionRight,
    PortfolioContext,
    PositionContext,
    ScanResult,
)
from options_seller.strategies.base import (
    StrategyBuilder,
    StrategyResult,
    pick_suggested,
    suggested_to_leg,
    template_leg,
)


class IronCondor(StrategyBuilder):
    name = "iron_condor"

    def build(
        self,
        scan: ScanResult,
        position: PositionContext | None = None,
        portfolio: PortfolioContext | None = None,
    ) -> Optional[StrategyResult]:
        reason = self.skip_reason(scan)
        if reason:
            return None

        price = float(scan.price or 0)
        width = self._spread_width_default(price) if price else 5.0
        target_dte = self._target_dte_spread()
        short_delta = self._ic_short_delta()

        dte_cfg = self.cfg.get("dte", {})
        dte_lo = int(dte_cfg.get("prefer_spread_min", 20))
        dte_hi = int(dte_cfg.get("prefer_spread_max", 45))
        delta_cfg = self.cfg.get("short_delta", {})
        lo = float(delta_cfg.get("min", 0.15))
        hi = float(delta_cfg.get("max", 0.30))

        legs_src = scan.options.suggested_legs()
        short_put = pick_suggested(
            legs_src,
            OptionRight.PUT,
            self.cfg,
            dte_lo=dte_lo,
            dte_hi=dte_hi,
            delta_lo=lo,
            delta_hi=hi,
            target_delta=short_delta,
            side="sell",
        )
        short_call = pick_suggested(
            legs_src,
            OptionRight.CALL,
            self.cfg,
            dte_lo=dte_lo,
            dte_hi=dte_hi,
            delta_lo=lo,
            delta_hi=hi,
            target_delta=short_delta,
            side="sell",
        )

        long_put = long_call = None
        if short_put is not None:
            puts = [
                L
                for L in legs_src
                if L.right == OptionRight.PUT
                and L.strike < short_put.strike
                and L.dte == short_put.dte
                and L.has_quotes()
            ]
            if puts:
                puts.sort(key=lambda L: abs(L.strike - (short_put.strike - width)))
                long_put = puts[0]
        if short_call is not None:
            calls = [
                L
                for L in legs_src
                if L.right == OptionRight.CALL
                and L.strike > short_call.strike
                and L.dte == short_call.dte
                and L.has_quotes()
            ]
            if calls:
                calls.sort(key=lambda L: abs(L.strike - (short_call.strike + width)))
                long_call = calls[0]

        if all(x is not None for x in (short_put, long_put, short_call, long_call)):
            assert short_put and long_put and short_call and long_call
            put_credit = (short_put.resolved_mid() or 0) - (long_put.resolved_mid() or 0)
            call_credit = (short_call.resolved_mid() or 0) - (long_call.resolved_mid() or 0)
            credit = max(0.0, put_credit) + max(0.0, call_credit)
            put_w = short_put.strike - long_put.strike
            call_w = long_call.strike - short_call.strike
            wing = max(put_w, call_w)
            max_loss = wing - credit
            plan = OrderPlan(
                strategy=self.name,
                underlying=scan.symbol,
                legs=[
                    suggested_to_leg(scan.symbol, short_put, Side.SELL),
                    suggested_to_leg(scan.symbol, long_put, Side.BUY),
                    suggested_to_leg(scan.symbol, short_call, Side.SELL),
                    suggested_to_leg(scan.symbol, long_call, Side.BUY),
                ],
                credit_debit="credit",
                net_premium=round(credit * 100, 2),
                max_profit=round(credit * 100, 2),
                max_loss=round(max_loss * 100, 2),
                capital_required=round(max_loss * 100, 2),
                is_template=False,
                target_dte=short_put.dte,
                target_delta=-short_delta,
                notes="Iron condor from suggested legs",
                metadata={"put_width": put_w, "call_width": call_w},
            )
            return StrategyResult(
                plan=plan,
                used_suggested=True,
                selected_legs=[short_put, long_put, short_call, long_call],
            )

        # Template
        sp = round(price * 0.95, 2) if price else None
        lp = round(sp - width, 2) if sp else None
        sc = round(price * 1.05, 2) if price else None
        lc = round(sc + width, 2) if sc else None
        frac = float(
            self.cfg.get("credit_spreads", {}).get("target_credit_fraction_of_width", 0.333)
        )
        # Rough: both wings contribute ~frac*width each → credit ~ 2/3 width max; use 2*frac/2
        est_credit = width * frac * 1.5
        plan = OrderPlan(
            strategy=self.name,
            underlying=scan.symbol,
            legs=[
                template_leg(
                    scan.symbol, option_type="put", side=Side.SELL,
                    target_dte=target_dte, target_delta=-short_delta, strike=sp,
                ),
                template_leg(
                    scan.symbol, option_type="put", side=Side.BUY,
                    target_dte=target_dte, target_delta=-short_delta * 0.4, strike=lp,
                ),
                template_leg(
                    scan.symbol, option_type="call", side=Side.SELL,
                    target_dte=target_dte, target_delta=short_delta, strike=sc,
                ),
                template_leg(
                    scan.symbol, option_type="call", side=Side.BUY,
                    target_dte=target_dte, target_delta=short_delta * 0.4, strike=lc,
                ),
            ],
            credit_debit="credit",
            net_premium=None,
            max_profit=None,
            max_loss=round((width - est_credit / 2) * 100, 2),
            capital_required=round((width - est_credit / 2) * 100, 2),
            is_template=True,
            target_dte=target_dte,
            target_delta=-short_delta,
            notes="Iron condor template — short ~0.16 delta when available",
            metadata={"width": width, "short_delta_target": short_delta},
        )
        return StrategyResult(plan=plan, used_suggested=False)
