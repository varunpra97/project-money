"""Shared strategy helpers and base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from options_seller.models.orders import Leg, OrderPlan, Side
from options_seller.models.scanner import (
    OptionRight,
    PortfolioContext,
    PositionContext,
    ScanResult,
    SuggestedLeg,
)


@dataclass
class StrategyResult:
    plan: OrderPlan
    used_suggested: bool = False
    selected_legs: list[SuggestedLeg] = field(default_factory=list)


def should_skip_earnings(scan: ScanResult, cfg: dict[str, Any]) -> bool:
    skip_days = int(cfg.get("earnings", {}).get("skip_within_days", 7))
    dte = scan.days_to_earnings
    if dte is None:
        return False
    return 0 <= dte <= skip_days


def iv_rank_ok(scan: ScanResult, cfg: dict[str, Any]) -> bool:
    """If ivRank is null, do not invent — treat as unknown (pass). If present, enforce min."""
    min_iv = float(cfg.get("iv_rank", {}).get("min", 30))
    ivr = scan.iv_rank
    if ivr is None:
        return True
    return ivr >= min_iv


def liquidity_ok_leg(leg: SuggestedLeg, cfg: dict[str, Any]) -> bool:
    liq = cfg.get("liquidity", {})
    min_oi = int(liq.get("min_open_interest", 100))
    max_ba = float(liq.get("max_bid_ask_spread", 0.15))
    if leg.openInterest is not None and leg.openInterest < min_oi:
        return False
    mid = leg.resolved_mid()
    if mid is None or mid <= 0:
        return False
    if leg.bid is not None and leg.ask is not None:
        spread = abs(leg.ask - leg.bid)
        if max_ba < 1.0:
            return (spread / mid) <= max_ba or spread <= 0.50
        return spread <= max_ba
    return True


def abs_delta(leg: SuggestedLeg) -> Optional[float]:
    if leg.delta is None:
        return None
    return abs(leg.delta)


def pick_suggested(
    legs: list[SuggestedLeg],
    right: OptionRight,
    cfg: dict[str, Any],
    *,
    dte_lo: int | None = None,
    dte_hi: int | None = None,
    delta_lo: float | None = None,
    delta_hi: float | None = None,
    target_delta: float | None = None,
    side: str | None = "sell",
) -> Optional[SuggestedLeg]:
    dte_cfg = cfg.get("dte", {})
    delta_cfg = cfg.get("short_delta", {})
    lo_d = dte_lo if dte_lo is not None else int(dte_cfg.get("min", 21))
    hi_d = dte_hi if dte_hi is not None else int(dte_cfg.get("max", 45))
    lo_delta = delta_lo if delta_lo is not None else float(delta_cfg.get("default_min", 0.20))
    hi_delta = delta_hi if delta_hi is not None else float(delta_cfg.get("default_max", 0.25))
    tgt = target_delta if target_delta is not None else (lo_delta + hi_delta) / 2.0

    pool: list[SuggestedLeg] = []
    for leg in legs:
        if leg.right is not None and leg.right != right:
            continue
        if not (lo_d <= leg.dte <= hi_d):
            continue
        if side and leg.side is not None and leg.side.value != side:
            continue
        if not leg.has_quotes():
            continue
        if not liquidity_ok_leg(leg, cfg):
            continue
        pool.append(leg)

    if not pool:
        return None

    scored: list[tuple[float, SuggestedLeg]] = []
    for leg in pool:
        ad = abs_delta(leg)
        if ad is None:
            score = 1.0 + abs(leg.dte - 35) * 0.01
        elif lo_delta <= ad <= hi_delta:
            score = abs(ad - tgt)
        else:
            score = 10.0 + abs(ad - tgt)
        scored.append((score, leg))
    scored.sort(key=lambda x: x[0])
    return scored[0][1]


def template_leg(
    underlying: str,
    *,
    option_type: str,
    side: Side,
    target_dte: int,
    target_delta: float,
    strike: Optional[float] = None,
) -> Leg:
    return Leg(
        symbol=underlying,
        option_type=option_type,
        strike=strike,
        dte=target_dte,
        side=side,
        quantity=1,
        limit_price=None,
        delta=target_delta if side == Side.SELL else None,
        template=True,
    )


def suggested_to_leg(underlying: str, sug: SuggestedLeg, side: Side | None = None) -> Leg:
    s = side
    if s is None and sug.side is not None:
        s = Side.BUY if sug.side.value == "buy" else Side.SELL
    if s is None:
        s = Side.SELL
    mid = sug.resolved_mid()
    ot = sug.right.value if sug.right else None
    return Leg(
        symbol=underlying,
        option_type=ot,
        strike=sug.strike,
        dte=sug.dte,
        expiry=sug.expiration,
        side=s,
        quantity=1,
        limit_price=mid,
        delta=sug.delta,
        open_interest=sug.openInterest,
        template=False,
    )


class StrategyBuilder(ABC):
    name: str = "base"

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg

    def skip_reason(self, scan: ScanResult) -> Optional[str]:
        if should_skip_earnings(scan, self.cfg):
            return "earnings within skip window"
        if not iv_rank_ok(scan, self.cfg):
            return "iv_rank below minimum"
        if scan.price is None:
            return "missing price"
        return None

    @abstractmethod
    def build(
        self,
        scan: ScanResult,
        position: PositionContext | None = None,
        portfolio: PortfolioContext | None = None,
    ) -> Optional[StrategyResult]:
        ...

    def _target_dte_csp_cc(self) -> int:
        d = self.cfg.get("dte", {})
        return int((int(d.get("prefer_csp_cc_min", 30)) + int(d.get("prefer_csp_cc_max", 45))) / 2)

    def _target_dte_spread(self) -> int:
        d = self.cfg.get("dte", {})
        return int((int(d.get("prefer_spread_min", 20)) + int(d.get("prefer_spread_max", 45))) / 2)

    def _target_short_delta(self) -> float:
        sd = self.cfg.get("short_delta", {})
        return (float(sd.get("default_min", 0.20)) + float(sd.get("default_max", 0.25))) / 2.0

    def _ic_short_delta(self) -> float:
        return float(self.cfg.get("short_delta", {}).get("iron_condor_target", 0.16))

    def _spread_width_default(self, price: float) -> float:
        # Heuristic width ~2.5% of price, rounded to common increments
        raw = max(1.0, round(price * 0.025, 0))
        return float(raw)
