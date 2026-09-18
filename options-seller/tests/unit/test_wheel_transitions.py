from __future__ import annotations

import pytest

from options_seller.strategies.wheel import (
    WheelState,
    apply_event,
    can_transition,
    next_action_state,
)


def test_happy_path_transitions():
    st = WheelState.IDLE
    st = apply_event(st, "fill_csp")
    assert st == WheelState.CSP_OPEN
    st = apply_event(st, "assigned")
    assert st == WheelState.ASSIGNED
    st = apply_event(st, "fill_cc")
    assert st == WheelState.CC_OPEN
    st = apply_event(st, "called_away")
    assert st == WheelState.CALLED_AWAY
    st = apply_event(st, "fill_csp")
    assert st == WheelState.CSP_OPEN


def test_expire_paths():
    assert apply_event(WheelState.CSP_OPEN, "expired") == WheelState.IDLE
    assert apply_event(WheelState.CC_OPEN, "expired") == WheelState.ASSIGNED


def test_invalid_transition_raises():
    with pytest.raises(ValueError):
        apply_event(WheelState.IDLE, "assigned")


def test_can_transition_table():
    assert can_transition(WheelState.IDLE, WheelState.CSP_OPEN)
    assert not can_transition(WheelState.IDLE, WheelState.ASSIGNED)


def test_next_action_with_shares():
    assert next_action_state("idle", shares=100) == WheelState.ASSIGNED
    assert next_action_state(None, shares=0) == WheelState.IDLE
    assert next_action_state("assigned", shares=100) == WheelState.ASSIGNED
