"""Bear call credit spread."""

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


class BearCallCreditSpread(StrategyBuilder):
    name = "bear_call_credit_spread"

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
        frac = float(
            self.cfg.get("credit_spreads", {}).get("target_credit_fraction_of_width", 0.333)
        )
        width = self._spread_width_default(price) if price else 5.0
        target_dte = self._target_dte_spread()
        target_delta = self._target_short_delta()

        dte_cfg = self.cfg.get("dte", {})
        dte_lo = int(dte_cfg.get("prefer_spread_min", 20))
        dte_hi = int(dte_cfg.get("prefer_spread_max", 45))

        legs_src = scan.options.suggested_legs()
        short = pick_suggested(
            legs_src, OptionRight.CALL, self.cfg, dte_lo=dte_lo, dte_hi=dte_hi, side="sell"
        )
        long = None
        if short is not None:
            calls = [
                L
                for L in legs_src
                if L.right == OptionRight.CALL
                and L.strike > short.strike
                and L.dte == short.dte
                and L.has_quotes()
            ]
            if calls:
                target = short.strike + width
                calls.sort(key=lambda L: abs(L.strike - target))
                long = calls[0]

        if short is not None and long is not None:
            credit = (short.resolved_mid() or 0) - (long.resolved_mid() or 0)
            credit = max(0.0, credit)
            width_act = long.strike - short.strike
            max_loss = width_act - credit
            plan = OrderPlan(
                strategy=self.name,
                underlying=scan.symbol,
                legs=[
                    suggested_to_leg(scan.symbol, short, Side.SELL),
                    suggested_to_leg(scan.symbol, long, Side.BUY),
                ],
                credit_debit="credit",
                net_premium=round(credit * 100, 2),
                max_profit=round(credit * 100, 2),
                max_loss=round(max_loss * 100, 2),
                capital_required=round(max_loss * 100, 2),
                is_template=False,
                target_dte=short.dte,
                target_delta=short.delta,
                notes=f"Bear call credit spread width={width_act}",
                metadata={"width": width_act, "target_credit_frac": frac},
            )
            return StrategyResult(plan=plan, used_suggested=True, selected_legs=[short, long])

        short_strike = round(price * 1.05, 2) if price else None
        long_strike = round(short_strike + width, 2) if short_strike else None
        target_credit = width * frac
        plan = OrderPlan(
            strategy=self.name,
            underlying=scan.symbol,
            legs=[
                template_leg(
                    scan.symbol,
                    option_type="call",
                    side=Side.SELL,
                    target_dte=target_dte,
                    target_delta=target_delta,
                    strike=short_strike,
                ),
                template_leg(
                    scan.symbol,
                    option_type="call",
                    side=Side.BUY,
                    target_dte=target_dte,
                    target_delta=target_delta * 0.4,
                    strike=long_strike,
                ),
            ],
            credit_debit="credit",
            net_premium=None,
            max_profit=None,
            max_loss=round((width - target_credit) * 100, 2),
            capital_required=round((width - target_credit) * 100, 2),
            is_template=True,
            target_dte=target_dte,
            target_delta=target_delta,
            notes="Bear call template — target credit ≈ 1/3 width",
            metadata={"width": width, "target_credit_per_share": target_credit},
        )
        return StrategyResult(plan=plan, used_suggested=False)
