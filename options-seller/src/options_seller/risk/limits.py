"""Portfolio risk math: per-position and aggregate hard caps (paper only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class RiskLimits:
    """Hard / soft portfolio risk profile."""

    max_portfolio_risk_usd: float = 50_000.0
    soft_warn_pct: float = 0.8
    auto_trim: bool = True

    @property
    def soft_warn_usd(self) -> float:
        return float(self.max_portfolio_risk_usd) * float(self.soft_warn_pct)


def risk_limits_from_config(cfg: dict[str, Any] | None = None) -> RiskLimits:
    """Build RiskLimits from defaults.yaml ``risk`` section (or overrides)."""
    risk = (cfg or {}).get("risk") or {}
    return RiskLimits(
        max_portfolio_risk_usd=float(risk.get("max_portfolio_risk_usd", 50_000)),
        soft_warn_pct=float(risk.get("soft_warn_pct", 0.8)),
        auto_trim=bool(risk.get("auto_trim", True)),
    )


def position_risk(pos: dict[str, Any]) -> float:
    """Per-position risk = max_loss if present and not null; else capital."""
    max_loss = pos.get("max_loss")
    if max_loss is not None:
        try:
            return float(max_loss)
        except (TypeError, ValueError):
            pass
    capital = pos.get("capital")
    if capital is not None:
        try:
            return float(capital)
        except (TypeError, ValueError):
            pass
    return 0.0


def plan_risk(plan: Any) -> float:
    """Risk of a new OrderPlan (same rules as position_risk)."""
    max_loss = getattr(plan, "max_loss", None)
    if isinstance(plan, dict):
        max_loss = plan.get("max_loss")
    if max_loss is not None:
        try:
            return float(max_loss)
        except (TypeError, ValueError):
            pass
    capital = getattr(plan, "capital_required", None)
    if isinstance(plan, dict):
        capital = plan.get("capital_required", plan.get("capital"))
    if capital is not None:
        try:
            return float(capital)
        except (TypeError, ValueError):
            pass
    return 0.0


def _open_only(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [p for p in positions if p.get("status") == "open"]


def aggregate_open_risk(positions: list[dict[str, Any]]) -> float:
    """Sum of per-position risk for status == 'open' only."""
    return float(sum(position_risk(p) for p in _open_only(positions)))


def headroom(
    positions: list[dict[str, Any]],
    limits: RiskLimits | None = None,
) -> float:
    """Remaining USD capacity under the hard cap (never negative for display math)."""
    lim = limits or RiskLimits()
    rem = float(lim.max_portfolio_risk_usd) - aggregate_open_risk(positions)
    return rem


def can_open(
    positions: list[dict[str, Any]],
    new_risk: float,
    limits: RiskLimits | None = None,
) -> tuple[bool, str]:
    """Return (allowed, reason). Reject when aggregate + new_risk > max."""
    lim = limits or RiskLimits()
    agg = aggregate_open_risk(positions)
    new_r = float(new_risk or 0.0)
    projected = agg + new_r
    rem = float(lim.max_portfolio_risk_usd) - agg
    if projected > float(lim.max_portfolio_risk_usd):
        return (
            False,
            (
                f"risk_rejected: open risk ${agg:,.2f} + new ${new_r:,.2f} = "
                f"${projected:,.2f} exceeds max ${lim.max_portfolio_risk_usd:,.2f} "
                f"(headroom ${rem:,.2f})"
            ),
        )
    return (
        True,
        (
            f"ok: projected open risk ${projected:,.2f} / "
            f"${lim.max_portfolio_risk_usd:,.2f} (headroom ${rem - new_r:,.2f})"
        ),
    )


def _trim_sort_key(pos: dict[str, Any]) -> tuple[float, float, str]:
    """Largest risk first; tie-break largest capital, then oldest (opened_at ascending → reverse)."""
    risk = position_risk(pos)
    capital = float(pos.get("capital") or 0.0)
    opened = str(pos.get("opened_at") or "")
    # Sort descending risk, descending capital, ascending opened_at (oldest first among ties)
    return (-risk, -capital, opened)


def pick_trim_targets(
    positions: list[dict[str, Any]],
    limits: RiskLimits | None = None,
) -> list[str]:
    """Ordered position ids to close until aggregate risk is under the hard cap."""
    lim = limits or RiskLimits()
    open_pos = list(_open_only(positions))
    ordered = sorted(open_pos, key=_trim_sort_key)
    targets: list[str] = []
    running = aggregate_open_risk(open_pos)
    for pos in ordered:
        if running <= float(lim.max_portfolio_risk_usd):
            break
        pid = pos.get("id")
        if not pid:
            continue
        targets.append(str(pid))
        running -= position_risk(pos)
    return targets


def evaluate_book(
    positions: list[dict[str, Any]],
    limits: RiskLimits | None = None,
) -> dict[str, Any]:
    """Status summary for CLI / dashboard."""
    lim = limits or RiskLimits()
    open_pos = _open_only(positions)
    agg = aggregate_open_risk(open_pos)
    rem = float(lim.max_portfolio_risk_usd) - agg
    soft = lim.soft_warn_usd
    hard_breach = agg > float(lim.max_portfolio_risk_usd)
    soft_warn = (not hard_breach) and agg >= soft
    if hard_breach:
        status = "hard_breach"
    elif soft_warn:
        status = "soft_warn"
    else:
        status = "ok"
    per = [
        {
            "id": p.get("id"),
            "underlying": p.get("underlying"),
            "strategy": p.get("strategy"),
            "risk": position_risk(p),
            "max_loss": p.get("max_loss"),
            "capital": p.get("capital"),
        }
        for p in sorted(open_pos, key=_trim_sort_key)
    ]
    return {
        "status": status,
        "aggregate_open_risk": round(agg, 2),
        "max_portfolio_risk_usd": float(lim.max_portfolio_risk_usd),
        "soft_warn_usd": round(soft, 2),
        "soft_warn_pct": float(lim.soft_warn_pct),
        "headroom": round(rem, 2),
        "utilization_pct": round(
            100.0 * agg / float(lim.max_portfolio_risk_usd)
            if lim.max_portfolio_risk_usd
            else 0.0,
            2,
        ),
        "hard_breach": hard_breach,
        "soft_warn": soft_warn,
        "open_count": len(open_pos),
        "trim_targets": pick_trim_targets(open_pos, lim),
        "positions_by_risk": per,
        "auto_trim": lim.auto_trim,
    }
