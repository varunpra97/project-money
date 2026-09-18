"""Strategy selector rules driven by scan bias + portfolio context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from options_seller.models.scanner import Bias, PortfolioContext, PositionContext, ScanResult
from options_seller.strategies import STRATEGY_REGISTRY, StrategyBuilder, StrategyResult
from options_seller.strategies.base import iv_rank_ok, should_skip_earnings
from options_seller.strategies.wheel import WheelState, next_action_state


@dataclass
class Selection:
    strategy_name: str
    reason: str
    result: StrategyResult


def _high_iv(scan: ScanResult, cfg: dict[str, Any]) -> bool:
    """True when ivRank present and >= min, or unknown (null) — do not invent."""
    return iv_rank_ok(scan, cfg)


def choose_strategy_name(
    scan: ScanResult,
    position: PositionContext,
    cfg: dict[str, Any],
) -> tuple[str, str]:
    """Return (strategy_name, reason) without building the plan."""
    # 1. Long shares → covered call (or wheel if already in wheel)
    if position.wheel_state and position.wheel_state not in ("", "idle", None):
        return "wheel", f"continue wheel (state={position.wheel_state})"

    if position.has_shares or position.shares_owned >= 100:
        if position.wheel_state in (WheelState.ASSIGNED.value, WheelState.CC_OPEN.value, "assigned", "cc_open"):
            return "wheel", "wheel assigned / shares held → covered call phase"
        return "covered_call", "long shares ≥ 100 → covered call"

    bias = scan.bias
    prefer_dr = bool(position.prefer_defined_risk)
    cash = position.cash_available
    cash_thresh = float(cfg.get("cash_threshold_for_defined_risk", 5000))
    if cash is not None and cash < cash_thresh:
        prefer_dr = True
    if cfg.get("prefer_defined_risk"):
        prefer_dr = True

    high_iv = _high_iv(scan, cfg)

    # Mildly bullish defined-risk → bull put (scanner bias is only bullish|bearish|neutral;
    # treat slight bullish via priceVsSma50Pct in (0, 2] as mild)
    mild_bull = (
        bias == Bias.BULLISH
        and scan.trend.priceVsSma50Pct is not None
        and 0 < scan.trend.priceVsSma50Pct <= 2.0
    )
    mild_bear = (
        bias == Bias.BEARISH
        and scan.trend.priceVsSma50Pct is not None
        and -2.0 <= scan.trend.priceVsSma50Pct < 0
    )

    if mild_bull and (prefer_dr or high_iv):
        return "bull_put_credit_spread", "mildly bullish → bull put credit spread"

    if bias == Bias.BULLISH and high_iv:
        if prefer_dr:
            return "bull_put_credit_spread", "bullish + defined-risk preference → bull put"
        return "cash_secured_put", "bullish + IV ok + cash → cash-secured put"

    if mild_bear and high_iv:
        return "bear_call_credit_spread", "mildly bearish + high IV → bear call spread"

    if bias == Bias.BEARISH and high_iv:
        return "bear_call_credit_spread", "bearish + high IV → bear call credit spread"

    if bias == Bias.NEUTRAL and high_iv:
        return "iron_condor", "neutral + high IV → iron condor"

    # Fallbacks
    if bias == Bias.BULLISH:
        return (
            "bull_put_credit_spread" if prefer_dr else "cash_secured_put",
            "bullish fallback",
        )
    if bias == Bias.BEARISH:
        return "bear_call_credit_spread", "bearish fallback"
    return "iron_condor", "neutral fallback"


def select_and_build(
    scan: ScanResult,
    cfg: dict[str, Any],
    portfolio: PortfolioContext | None = None,
) -> Optional[Selection]:
    portfolio = portfolio or PortfolioContext()
    position = portfolio.for_symbol(scan.symbol)

    if should_skip_earnings(scan, cfg):
        return None
    if scan.price is None:
        return None

    # Explicit wheel continuation even if shares just assigned
    if position.wheel_state:
        phase = next_action_state(position.wheel_state, position.shares_owned)
        if position.wheel_state not in (None, "", "idle") or phase != WheelState.IDLE:
            name, reason = "wheel", f"wheel state machine ({position.wheel_state})"
            # If idle with no shares and no active wheel, fall through to normal rules
            if position.wheel_state in (None, "", "idle") and position.shares_owned < 100:
                name, reason = choose_strategy_name(scan, position, cfg)
            else:
                name, reason = "wheel", f"continue wheel (state={position.wheel_state})"
        else:
            name, reason = choose_strategy_name(scan, position, cfg)
    else:
        name, reason = choose_strategy_name(scan, position, cfg)

    # If scanner suggested a strategy name, prefer it when present
    hinted = scan.options.suggested_strategy_name()
    if hinted and hinted in STRATEGY_REGISTRY:
        name, reason = hinted, f"options.suggested strategy hint={hinted}"

    builder_cls: type[StrategyBuilder] = STRATEGY_REGISTRY[name]
    builder = builder_cls(cfg)
    result = builder.build(scan, position, portfolio)
    if result is None:
        return None
    result.plan.metadata["selection_reason"] = reason
    return Selection(strategy_name=name, reason=reason, result=result)
