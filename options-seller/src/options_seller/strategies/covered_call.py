"""Covered call strategy."""

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


class CoveredCall(StrategyBuilder):
    name = "covered_call"

    def build(
        self,
        scan: ScanResult,
        position: PositionContext | None = None,
        portfolio: PortfolioContext | None = None,
    ) -> Optional[StrategyResult]:
        reason = self.skip_reason(scan)
        if reason:
            return None

        shares = position.shares_owned if position else 0
        if shares < 100 and not (position and position.has_shares):
            # Still allow template build when selector already chose CC
            pass

        price = float(scan.price or 0)
        dte_cfg = self.cfg.get("dte", {})
        dte_lo = int(dte_cfg.get("prefer_csp_cc_min", 30))
        dte_hi = int(dte_cfg.get("prefer_csp_cc_max", 45))
        target_dte = self._target_dte_csp_cc()
        target_delta = self._target_short_delta()

        legs_src = scan.options.suggested_legs()
        short = pick_suggested(
            legs_src,
            OptionRight.CALL,
            self.cfg,
            dte_lo=dte_lo,
            dte_hi=dte_hi,
            side="sell",
        )

        qty = max(1, shares // 100) if shares >= 100 else 1

        if short is not None:
            mid = short.resolved_mid() or 0.0
            credit = mid * 100 * qty
            plan = OrderPlan(
                strategy=self.name,
                underlying=scan.symbol,
                legs=[suggested_to_leg(scan.symbol, short, Side.SELL)],
                credit_debit="credit",
                net_premium=round(credit, 2),
                max_profit=round(credit, 2),
                max_loss=None,  # stock downside theoretically unlimited vs cost basis
                capital_required=round(price * 100 * qty, 2) if price else None,
                is_template=False,
                target_dte=short.dte,
                target_delta=short.delta,
                notes=f"Covered call x{qty} from suggested",
                metadata={"contracts": qty, "shares_owned": shares},
            )
            plan.legs[0].quantity = qty
            return StrategyResult(plan=plan, used_suggested=True, selected_legs=[short])

        approx_strike = round(price * 1.05, 2) if price else None
        leg = template_leg(
            scan.symbol,
            option_type="call",
            side=Side.SELL,
            target_dte=target_dte,
            target_delta=target_delta,
            strike=approx_strike,
        )
        leg.quantity = qty
        plan = OrderPlan(
            strategy=self.name,
            underlying=scan.symbol,
            legs=[leg],
            credit_debit="credit",
            net_premium=None,
            max_profit=None,
            max_loss=None,
            capital_required=round(price * 100 * qty, 2) if price else None,
            is_template=True,
            target_dte=target_dte,
            target_delta=target_delta,
            notes="CC template — options.suggested unavailable",
            metadata={"contracts": qty, "approx_strike": approx_strike},
        )
        return StrategyResult(plan=plan, used_suggested=False)
