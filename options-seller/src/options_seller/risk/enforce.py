"""Enforce hard portfolio risk by trimming highest-risk open paper positions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING

from options_seller.risk.limits import (
    RiskLimits,
    aggregate_open_risk,
    evaluate_book,
    pick_trim_targets,
    position_risk,
    risk_limits_from_config,
)

if TYPE_CHECKING:
    from options_seller.execution.paper import PaperExecutor


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def enforce_hard_limits(
    executor: "PaperExecutor",
    limits: RiskLimits | None = None,
) -> dict[str, Any]:
    """Close open positions (highest risk first) until aggregate risk <= hard cap.

    Uses ``PaperExecutor.close_position``. Logs each trim on portfolio
    ``risk_events`` and relies on close fills for the activity trail.
    PAPER ONLY — never places live broker orders.
    """
    lim = limits or RiskLimits()
    before = evaluate_book(executor.portfolio.get("positions", []), lim)
    actions: list[dict[str, Any]] = []

    if not before["hard_breach"]:
        return {
            "trimmed": False,
            "actions": actions,
            "before": before,
            "after": before,
            "message": "aggregate open risk within hard cap; no trim",
        }

    targets = list(before["trim_targets"])
    for pid in targets:
        pos = executor.get_position(pid)
        if pos is None or pos.get("status") != "open":
            continue
        risk_before = position_risk(pos)
        closed = executor.close_position(pid)
        import uuid

        event = {
            "id": str(uuid.uuid4()),
            "type": "risk_trim",
            "position_id": pid,
            "underlying": closed.get("underlying"),
            "strategy": closed.get("strategy"),
            "risk_freed": risk_before,
            "realized_pnl": closed.get("realized_pnl"),
            "ts": _utc_now(),
            "max_portfolio_risk_usd": lim.max_portfolio_risk_usd,
            "capital_required": closed.get("capital"),
            "max_loss": closed.get("max_loss"),
            "reason": (
                f"auto-trim: closed largest risk ${risk_before:,.2f} "
                f"to enforce ${lim.max_portfolio_risk_usd:,.0f} cap"
            ),
        }
        executor.portfolio.setdefault("risk_events", []).append(event)
        executor.portfolio.setdefault("fills", []).append(dict(event))
        executor.portfolio["auto_trim_last"] = dict(event)
        # Persist risk_events (close_position already saved once)
        if hasattr(executor, "_save"):
            executor._save()
        actions.append(event)
        # Stop early if already under cap (defensive; targets should be exact)
        if aggregate_open_risk(executor.portfolio.get("positions", [])) <= float(
            lim.max_portfolio_risk_usd
        ):
            break

    after = evaluate_book(executor.portfolio.get("positions", []), lim)
    return {
        "trimmed": bool(actions),
        "actions": actions,
        "before": before,
        "after": after,
        "message": (
            f"trimmed {len(actions)} position(s); "
            f"risk ${before['aggregate_open_risk']:,.2f} → ${after['aggregate_open_risk']:,.2f}"
        ),
    }


def limits_from_defaults() -> RiskLimits:
    """Load RiskLimits from package defaults.yaml."""
    from options_seller.config import load_defaults

    return risk_limits_from_config(load_defaults())
