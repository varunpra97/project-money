"""Cash-secured put strategy."""

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


class CashSecuredPut(StrategyBuilder):
    name = "cash_secured_put"

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
        dte_cfg = self.cfg.get("dte", {})
        dte_lo = int(dte_cfg.get("prefer_csp_cc_min", 30))
        dte_hi = int(dte_cfg.get("prefer_csp_cc_max", 45))
        target_dte = self._target_dte_csp_cc()
        target_delta = -self._target_short_delta()

        legs_src = scan.options.suggested_legs()
        short = pick_suggested(
            legs_src,
            OptionRight.PUT,
            self.cfg,
            dte_lo=dte_lo,
            dte_hi=dte_hi,
            side="sell",
        )

        if short is not None:
            mid = short.resolved_mid() or 0.0
            credit = mid * 100
            capital = short.strike * 100
            plan = OrderPlan(
                strategy=self.name,
                underlying=scan.symbol,
                legs=[suggested_to_leg(scan.symbol, short, Side.SELL)],
                credit_debit="credit",
                net_premium=round(credit, 2),
                max_profit=round(credit, 2),
                max_loss=round(capital - credit, 2),
                capital_required=round(capital, 2),
                is_template=False,
                target_dte=short.dte,
                target_delta=short.delta,
                notes="CSP from scanner suggested leg",
            )
            return StrategyResult(plan=plan, used_suggested=True, selected_legs=[short])

        # Template when options null / no usable suggested
        approx_strike = round(price * 0.95, 2) if price else None
        plan = OrderPlan(
            strategy=self.name,
            underlying=scan.symbol,
            legs=[
                template_leg(
                    scan.symbol,
                    option_type="put",
                    side=Side.SELL,
                    target_dte=target_dte,
                    target_delta=target_delta,
                    strike=approx_strike,
                )
            ],
            credit_debit="credit",
            net_premium=None,
            max_profit=None,
            max_loss=None,
            capital_required=round(approx_strike * 100, 2) if approx_strike else None,
            is_template=True,
            target_dte=target_dte,
            target_delta=target_delta,
            notes="CSP template — options.suggested unavailable; target DTE/delta only",
            metadata={"approx_strike": approx_strike, "reason": "no_suggested_quotes"},
        )
        return StrategyResult(plan=plan, used_suggested=False)
