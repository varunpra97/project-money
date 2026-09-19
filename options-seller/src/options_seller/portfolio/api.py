"""Pure helpers the dashboard imports for paper portfolio metrics."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from options_seller.execution.paper import PaperExecutor
from options_seller.portfolio.celebrity_priority import rollup_ticker
from options_seller.paths import data_dir

# Default path under the options-seller project
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PAPER_PATH = data_dir() / "paper_portfolio.json"


def load_executor(
    store_path: Path | str | None = None,
    *,
    slippage: float = 0.02,
) -> PaperExecutor:
    path = Path(store_path) if store_path else DEFAULT_PAPER_PATH
    return PaperExecutor(store_path=path, slippage=slippage)


def list_open(executor: PaperExecutor | None = None, **kwargs: Any) -> list[dict[str, Any]]:
    ex = executor or load_executor(**{k: v for k, v in kwargs.items() if k == "store_path"})
    if executor is None and "store_path" in kwargs:
        ex = load_executor(kwargs["store_path"])
    elif executor is None:
        ex = load_executor()
    return ex.list_open()


def list_closed(executor: PaperExecutor | None = None, **kwargs: Any) -> list[dict[str, Any]]:
    ex = executor or load_executor()
    if "store_path" in kwargs and executor is None:
        ex = load_executor(kwargs["store_path"])
    return ex.list_closed()


def list_fills(executor: PaperExecutor | None = None, **kwargs: Any) -> list[dict[str, Any]]:
    ex = executor or load_executor()
    if "store_path" in kwargs and executor is None:
        ex = load_executor(kwargs["store_path"])
    return ex.list_fills()


def _is_today(iso: str | None) -> bool:
    if not iso:
        return False
    try:
        ts = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return False
    now = datetime.now(timezone.utc)
    return ts.astimezone(timezone.utc).date() == now.date()


def summary_metrics(executor: PaperExecutor | None = None, **kwargs: Any) -> dict[str, Any]:
    """Account header metrics for the dashboard."""
    if executor is None:
        executor = load_executor(kwargs.get("store_path"))
    pf = executor.portfolio
    open_pos = executor.list_open()
    closed = executor.list_closed()

    cash = float(pf.get("cash", 0))
    starting = float(pf.get("starting_cash", cash))
    unrealized = sum(float(p.get("unrealized_pnl") or 0) for p in open_pos if p.get("status") == "open")
    realized_life = float(pf.get("realized_pnl_lifetime", 0))
    # Also sum closed positions in case lifetime drifted
    realized_from_closed = sum(float(p.get("realized_pnl") or 0) for p in closed)
    realized_total = realized_life if realized_life else realized_from_closed

    premium = float(pf.get("premium_collected_lifetime", 0))
    capital_secured = sum(
        float(p.get("capital") or 0)
        for p in open_pos
        if p.get("status") == "open" and p.get("capital")
    )
    # Buying power ≈ cash - capital secured for CSPs (simplified)
    buying_power = cash  # cash already includes credits; capital is reserved conceptually
    net_liq = cash + unrealized  # paper approximation

    # Day P&L: realized closed today + mark change on opens (unrealized as proxy)
    day_realized = sum(
        float(p.get("realized_pnl") or 0)
        for p in closed
        if _is_today(p.get("closed_at"))
    )
    day_pnl = day_realized + unrealized  # EST: no prior-day mark snapshot

    return {
        "net_liquidation": round(net_liq, 2),
        "cash": round(cash, 2),
        "starting_cash": round(starting, 2),
        "day_pnl": round(day_pnl, 2),
        "day_pnl_note": "EST — realized today + current unrealized (no prior mark)",
        "unrealized_pnl": round(unrealized, 2),
        "realized_pnl": round(realized_total, 2),
        "premium_collected": round(premium, 2),
        "open_positions": len([p for p in open_pos if p.get("status") == "open"]),
        "planned_positions": len([p for p in open_pos if p.get("status") == "planned"]),
        "buying_power": round(buying_power, 2),
        "capital_secured": round(capital_secured, 2),
    }


def _leg_delta_est(leg: dict[str, Any]) -> Optional[float]:
    """Position delta contribution EST. Uses leg.delta if present, else strategy templates."""
    side = (leg.get("side") or "sell").lower()
    qty = int(leg.get("quantity") or 1)
    sign = -1.0 if side in ("sell", "short") else 1.0
    d = leg.get("delta")
    if d is not None:
        # Scanner deltas are usually signed (puts negative). For short put, sell * (-0.2) = +0.2
        # Position greek: side_sign * delta * 100 * qty
        return sign * float(d) * 100.0 * qty
    opt = (leg.get("option_type") or "").lower()
    # Rough template defaults when delta missing
    if opt == "put":
        approx = -0.22  # short-put target ~0.22 abs
    elif opt == "call":
        approx = 0.22
    else:
        return None
    return sign * approx * 100.0 * qty


def portfolio_greeks_est(executor: PaperExecutor | None = None, **kwargs: Any) -> dict[str, Any]:
    """Rough portfolio Greeks from position deltas/templates. Always labeled EST."""
    if executor is None:
        executor = load_executor(kwargs.get("store_path"))
    open_pos = [p for p in executor.list_open() if p.get("status") == "open"]

    delta = 0.0
    theta = 0.0
    gamma = 0.0
    vega = 0.0
    any_real_delta = False

    for pos in open_pos:
        legs = pos.get("legs") or []
        credit = float(pos.get("credit") or 0)
        dte = pos.get("dte") or 30
        pos_delta = 0.0
        for leg in legs:
            ld = _leg_delta_est(leg)
            if ld is not None:
                if leg.get("delta") is not None:
                    any_real_delta = True
                pos_delta += ld
        delta += pos_delta
        # Theta EST: credit / DTE for short premium (positive for sellers)
        if pos.get("credit_debit") == "credit" and credit > 0:
            theta += credit / max(int(dte), 1)
        # Gamma / vega: very rough placeholders from |delta|
        gamma += -abs(pos_delta) * 0.01  # short options ≈ negative gamma
        vega += -abs(pos_delta) * 0.05

    return {
        "delta": round(delta, 1),
        "theta": round(theta, 2),
        "gamma": round(gamma, 2),
        "vega": round(vega, 2),
        "estimated": True,
        "label": "EST.",
        "note": (
            "Portfolio Greeks are rough estimates from leg deltas/templates "
            + ("(some live deltas present). " if any_real_delta else "(template defaults). ")
            + "Not live broker Greeks."
        ),
    }


def seed_demo_book(
    executor: PaperExecutor | None = None,
    *,
    store_path: Path | str | None = None,
    reset: bool = True,
) -> list[dict[str, Any]]:
    """Open a few realistic paper positions with synthetic premiums."""
    ex = executor or load_executor(store_path)
    if reset:
        ex.reset()

    seeded: list[dict[str, Any]] = []

    # Closed winner first (activity/income) — keep final open risk ~$35.8k under $50k cap
    closed = ex.open_demo_position(
        underlying="META",
        strategy="cash_secured_put",
        legs=[
            {
                "symbol": "META",
                "option_type": "put",
                "strike": 480.0,
                "dte": 14,
                "side": "sell",
                "quantity": 1,
                "delta": -0.18,
            }
        ],
        credit=275.0,
        capital=48000.0,
        max_profit=275.0,
        max_loss=47725.0,
        dte=14,
        underlying_price=510.0,
        notes="demo closed CSP",
        mark_fraction=0.20,
    )
    ex.close_position(closed["id"], price=55.0)

    seeded.append(
        ex.open_demo_position(
            underlying="AAPL",
            strategy="cash_secured_put",
            legs=[
                {
                    "symbol": "AAPL",
                    "option_type": "put",
                    "strike": 210.0,
                    "dte": 32,
                    "side": "sell",
                    "quantity": 1,
                    "delta": -0.22,
                    "template": False,
                }
            ],
            credit=320.0,
            capital=21000.0,
            max_profit=320.0,
            max_loss=20680.0,
            dte=32,
            underlying_price=225.0,
            notes="demo CSP",
            mark_fraction=0.45,
        )
    )
    seeded.append(
        ex.open_demo_position(
            underlying="MSFT",
            strategy="bull_put_credit_spread",
            legs=[
                {
                    "symbol": "MSFT",
                    "option_type": "put",
                    "strike": 400.0,
                    "dte": 28,
                    "side": "sell",
                    "quantity": 1,
                    "delta": -0.25,
                },
                {
                    "symbol": "MSFT",
                    "option_type": "put",
                    "strike": 390.0,
                    "dte": 28,
                    "side": "buy",
                    "quantity": 1,
                    "delta": -0.12,
                },
            ],
            credit=185.0,
            capital=1000.0,
            max_profit=185.0,
            max_loss=815.0,
            dte=28,
            underlying_price=420.0,
            notes="demo bull put",
            mark_fraction=0.40,
        )
    )
    seeded.append(
        ex.open_demo_position(
            underlying="SPY",
            strategy="iron_condor",
            legs=[
                {"symbol": "SPY", "option_type": "put", "strike": 520.0, "dte": 25, "side": "buy", "quantity": 1, "delta": -0.08},
                {"symbol": "SPY", "option_type": "put", "strike": 530.0, "dte": 25, "side": "sell", "quantity": 1, "delta": -0.16},
                {"symbol": "SPY", "option_type": "call", "strike": 560.0, "dte": 25, "side": "sell", "quantity": 1, "delta": 0.16},
                {"symbol": "SPY", "option_type": "call", "strike": 570.0, "dte": 25, "side": "buy", "quantity": 1, "delta": 0.08},
            ],
            credit=140.0,
            capital=1000.0,
            max_profit=140.0,
            max_loss=860.0,
            dte=25,
            underlying_price=545.0,
            notes="demo iron condor",
            mark_fraction=0.50,
        )
    )
    seeded.append(
        ex.open_demo_position(
            underlying="NVDA",
            strategy="covered_call",
            legs=[
                {
                    "symbol": "NVDA",
                    "option_type": "call",
                    "strike": 140.0,
                    "dte": 21,
                    "side": "sell",
                    "quantity": 1,
                    "delta": 0.28,
                }
            ],
            credit=210.0,
            capital=13000.0,
            max_profit=210.0,
            max_loss=None,
            dte=21,
            underlying_price=128.0,
            notes="demo covered call",
            mark_fraction=0.60,
        )
    )
    seeded.append(
        ex.open_demo_position(
            underlying="AMD",
            strategy="bear_call_credit_spread",
            legs=[
                {"symbol": "AMD", "option_type": "call", "strike": 170.0, "dte": 30, "side": "sell", "quantity": 1, "delta": 0.24},
                {"symbol": "AMD", "option_type": "call", "strike": 175.0, "dte": 30, "side": "buy", "quantity": 1, "delta": 0.14},
            ],
            credit=95.0,
            capital=500.0,
            max_profit=95.0,
            max_loss=405.0,
            dte=30,
            underlying_price=158.0,
            notes="demo bear call",
            mark_fraction=0.35,
        )
    )

    return seeded


def _parse_ts(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def days_held(opened_at: str | None, closed_at: str | None = None) -> float | None:
    """Calendar days between open and close (or now if still open)."""
    start = _parse_ts(opened_at)
    if start is None:
        return None
    end = _parse_ts(closed_at) or datetime.now(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return round((end - start).total_seconds() / 86400.0, 2)


def pct_of_max_profit(unrealized: Any, max_profit: Any) -> float | None:
    """Unrealized as % of max profit when max_profit > 0."""
    try:
        mp = float(max_profit) if max_profit is not None else None
        ur = float(unrealized) if unrealized is not None else None
    except (TypeError, ValueError):
        return None
    if mp is None or ur is None or mp <= 0:
        return None
    return round(ur / mp * 100.0, 1)


def _perf_bucket() -> dict[str, Any]:
    return {
        "open_count": 0,
        "unrealized": 0.0,
        "closed_count": 0,
        "realized": 0.0,
        "wins": 0,
        "losses": 0,
        "win_sum": 0.0,
        "loss_sum": 0.0,
        "premium_collected": 0.0,
        "capital": 0.0,
    }


def _finalize_perf(key_name: str, key: str, b: dict[str, Any]) -> dict[str, Any]:
    closed = int(b["closed_count"])
    wins = int(b["wins"])
    losses = int(b["losses"])
    decided = wins + losses
    win_rate = round(wins / decided * 100.0, 1) if decided else None
    avg_win = round(b["win_sum"] / wins, 2) if wins else None
    avg_loss = round(b["loss_sum"] / losses, 2) if losses else None
    return {
        key_name: key,
        "open_count": int(b["open_count"]),
        "unrealized": round(float(b["unrealized"]), 2),
        "closed_count": closed,
        "realized": round(float(b["realized"]), 2),
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "premium_collected": round(float(b["premium_collected"]), 2),
        "capital": round(float(b["capital"]), 2),
    }


def _accumulate_positions(
    positions: list[dict[str, Any]], key_fn
) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for p in positions:
        key = key_fn(p) or "?"
        b = buckets.setdefault(key, _perf_bucket())
        status = p.get("status")
        credit = p.get("credit")
        if credit is not None and p.get("credit_debit", "credit") == "credit":
            # Count premium on any filled (open or closed) credit trade
            if status in ("open", "closed"):
                b["premium_collected"] += float(credit)
        if status == "open":
            b["open_count"] += 1
            b["unrealized"] += float(p.get("unrealized_pnl") or 0)
            b["capital"] += float(p.get("capital") or 0)
        elif status == "closed":
            b["closed_count"] += 1
            rpnl = float(p.get("realized_pnl") or 0)
            b["realized"] += rpnl
            if rpnl > 0:
                b["wins"] += 1
                b["win_sum"] += rpnl
            elif rpnl < 0:
                b["losses"] += 1
                b["loss_sum"] += rpnl
            # rpnl == 0: neither win nor loss
        # planned: ignore for P&L tables
    return buckets


def strategy_performance(executor: PaperExecutor | None = None, **kwargs: Any) -> list[dict[str, Any]]:
    """Per-strategy open/closed P&L, win rate, premium. Sorted by open_count then name."""
    if executor is None:
        executor = load_executor(kwargs.get("store_path"))
    positions = executor.portfolio.get("positions", [])
    buckets = _accumulate_positions(positions, lambda p: p.get("strategy"))
    rows = [_finalize_perf("strategy", k, v) for k, v in buckets.items()]
    rows.sort(key=lambda r: (-r["open_count"], -r["closed_count"], r["strategy"] or ""))
    return rows


def ticker_performance(executor: PaperExecutor | None = None, **kwargs: Any) -> list[dict[str, Any]]:
    """Per-ticker open/closed P&L, win rate, premium. Sorted by open_count then name.

    Dual-class shares (GOOG/GOOGL) roll up under GOOGL so they are not double-counted.
    """
    if executor is None:
        executor = load_executor(kwargs.get("store_path"))
    positions = executor.portfolio.get("positions", [])
    buckets = _accumulate_positions(positions, lambda p: rollup_ticker(p.get("underlying")))
    rows = [_finalize_perf("ticker", k, v) for k, v in buckets.items()]
    rows.sort(key=lambda r: (-r["open_count"], -r["closed_count"], r["ticker"] or ""))
    return rows


def strategies_in_play(executor: PaperExecutor | None = None, **kwargs: Any) -> list[dict[str, Any]]:
    """Strategies with ≥1 open position — for the horizontal strip."""
    rows = strategy_performance(executor, **kwargs)
    return [r for r in rows if r["open_count"] >= 1]
