"""Wheel strategy state machine: CSP → assigned → CC → called away → CSP."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from options_seller.models.orders import OrderPlan
from options_seller.models.scanner import PortfolioContext, PositionContext, ScanResult
from options_seller.strategies.base import StrategyBuilder, StrategyResult
from options_seller.strategies.cash_secured_put import CashSecuredPut
from options_seller.strategies.covered_call import CoveredCall


class WheelState(str, Enum):
    IDLE = "idle"
    CSP_OPEN = "csp_open"
    ASSIGNED = "assigned"
    CC_OPEN = "cc_open"
    CALLED_AWAY = "called_away"


# Valid transitions for the wheel state machine
TRANSITIONS: dict[WheelState, list[WheelState]] = {
    WheelState.IDLE: [WheelState.CSP_OPEN],
    WheelState.CSP_OPEN: [WheelState.ASSIGNED, WheelState.IDLE],  # assigned or expired worthless
    WheelState.ASSIGNED: [WheelState.CC_OPEN],
    WheelState.CC_OPEN: [WheelState.CALLED_AWAY, WheelState.ASSIGNED],  # called or expired
    WheelState.CALLED_AWAY: [WheelState.IDLE, WheelState.CSP_OPEN],
}


def next_action_state(state: WheelState | str | None, shares: int = 0) -> WheelState:
    """Determine which wheel phase to trade next."""
    if state is None or state == "" or state == WheelState.IDLE.value:
        if shares >= 100:
            return WheelState.ASSIGNED
        return WheelState.IDLE
    try:
        st = WheelState(state) if not isinstance(state, WheelState) else state
    except ValueError:
        return WheelState.IDLE if shares < 100 else WheelState.ASSIGNED

    if st in (WheelState.IDLE, WheelState.CALLED_AWAY):
        return WheelState.IDLE if shares < 100 else WheelState.ASSIGNED
    if st == WheelState.CSP_OPEN:
        return WheelState.CSP_OPEN  # hold / manage existing
    if st in (WheelState.ASSIGNED, WheelState.CC_OPEN):
        return WheelState.ASSIGNED if shares >= 100 else WheelState.IDLE
    return st


def can_transition(current: WheelState, new: WheelState) -> bool:
    return new in TRANSITIONS.get(current, [])


def apply_event(current: WheelState, event: str) -> WheelState:
    """Apply lifecycle event: fill_csp, assigned, fill_cc, called_away, expired."""
    event = event.lower()
    if event == "fill_csp" and current in (WheelState.IDLE, WheelState.CALLED_AWAY):
        return WheelState.CSP_OPEN
    if event == "assigned" and current == WheelState.CSP_OPEN:
        return WheelState.ASSIGNED
    if event == "expired" and current == WheelState.CSP_OPEN:
        return WheelState.IDLE
    if event == "fill_cc" and current == WheelState.ASSIGNED:
        return WheelState.CC_OPEN
    if event == "called_away" and current == WheelState.CC_OPEN:
        return WheelState.CALLED_AWAY
    if event == "expired" and current == WheelState.CC_OPEN:
        return WheelState.ASSIGNED
    if event == "reset":
        return WheelState.IDLE
    raise ValueError(f"Invalid wheel transition: {current.value} + {event}")


class WheelStrategy(StrategyBuilder):
    name = "wheel"

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
        raw_state = position.wheel_state if position else None
        phase = next_action_state(raw_state, shares)

        if phase in (WheelState.ASSIGNED, WheelState.CC_OPEN) or shares >= 100:
            inner = CoveredCall(self.cfg).build(scan, position, portfolio)
            action = "covered_call"
            new_state = WheelState.CC_OPEN
        else:
            inner = CashSecuredPut(self.cfg).build(scan, position, portfolio)
            action = "cash_secured_put"
            new_state = WheelState.CSP_OPEN

        if inner is None:
            return None

        plan = inner.plan.model_copy(deep=True)
        plan.strategy = self.name
        plan.notes = f"Wheel → {action} (state {phase.value} → {new_state.value}); {plan.notes}"
        plan.metadata = {
            **plan.metadata,
            "wheel_phase": phase.value,
            "wheel_next_state": new_state.value,
            "inner_strategy": action,
        }
        return StrategyResult(
            plan=plan,
            used_suggested=inner.used_suggested,
            selected_legs=inner.selected_legs,
        )


def wheel_plan_to_order(result: StrategyResult) -> OrderPlan:
    return result.plan
