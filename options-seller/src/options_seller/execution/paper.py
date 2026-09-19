"""Paper executor — fills at mid with optional slippage; first-class positions."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from options_seller.models.orders import OrderPlan, TradeTicket
from options_seller.execution.broker import plan_to_ticket
from options_seller.risk.limits import RiskLimits, aggregate_open_risk, headroom as risk_headroom

DEFAULT_STARTING_CASH = 100_000.0
DEFAULT_MAX_PORTFOLIO_RISK = 50_000.0  # $50k hard gate


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_portfolio(starting_cash: float = DEFAULT_STARTING_CASH) -> dict[str, Any]:
    return {
        "cash": float(starting_cash),
        "starting_cash": float(starting_cash),
        "premium_collected_lifetime": 0.0,
        "realized_pnl_lifetime": 0.0,
        "positions": [],
        "fills": [],
        "risk_events": [],
        "version": 2,
    }


def _normalize_portfolio(raw: dict[str, Any]) -> dict[str, Any]:
    """Migrate legacy v1 paper books to first-class position records."""
    out = dict(raw)
    out.setdefault("cash", DEFAULT_STARTING_CASH)
    out.setdefault("starting_cash", float(out.get("cash", DEFAULT_STARTING_CASH)))
    out.setdefault("premium_collected_lifetime", 0.0)
    out.setdefault("realized_pnl_lifetime", 0.0)
    out.setdefault("fills", [])
    out.setdefault("positions", [])
    out.setdefault("risk_events", [])
    out.setdefault("version", 2)
    out.setdefault("max_portfolio_risk_usd", DEFAULT_MAX_PORTFOLIO_RISK)
    out.setdefault("last_risk_event", None)
    out.setdefault("auto_trim_last", None)

    migrated: list[dict[str, Any]] = []
    for p in out["positions"]:
        if "id" in p and "status" in p and "legs" in p:
            migrated.append(p)
            continue
        # Legacy stub: {underlying, strategy, capital, fill_id}
        fill = next((f for f in out["fills"] if f.get("id") == p.get("fill_id")), None)
        legs = (fill or {}).get("legs", [])
        credit = (fill or {}).get("fill_price")
        migrated.append(
            {
                "id": p.get("id") or str(uuid.uuid4()),
                "underlying": p.get("underlying") or (fill or {}).get("underlying"),
                "strategy": p.get("strategy") or (fill or {}).get("strategy"),
                "legs": legs,
                "credit": credit,
                "capital": p.get("capital") or (fill or {}).get("capital_required"),
                "max_profit": (fill or {}).get("max_profit"),
                "max_loss": (fill or {}).get("max_loss"),
                "opened_at": (fill or {}).get("ts") or _utc_now(),
                "status": "open",
                "closed_at": None,
                "close_price": None,
                "realized_pnl": None,
                "unrealized_pnl": 0.0,
                "mark": credit,
                "underlying_price_at_open": None,
                "underlying_mark": None,
                "dte": _dte_from_legs(legs),
                "expiry": None,
                "notes": "migrated from legacy paper book",
                "credit_debit": "credit",
                "fill_id": p.get("fill_id"),
                "is_template": False,
            }
        )
    out["positions"] = migrated
    return out


def _dte_from_legs(legs: list[Any]) -> Optional[int]:
    dtes = []
    for leg in legs or []:
        if isinstance(leg, dict) and leg.get("dte") is not None:
            dtes.append(int(leg["dte"]))
        elif hasattr(leg, "dte") and leg.dte is not None:
            dtes.append(int(leg.dte))
    return min(dtes) if dtes else None


def _leg_dump(leg: Any) -> dict[str, Any]:
    if hasattr(leg, "model_dump"):
        return leg.model_dump(mode="json")
    if isinstance(leg, dict):
        return leg
    return dict(leg)


class PaperExecutor:
    """Dry-run fills only. Never contacts a live broker."""

    def __init__(
        self,
        store_path: Path | str = "data/paper_portfolio.json",
        *,
        slippage: float = 0.02,
        use_sqlite: bool = False,
        starting_cash: float = DEFAULT_STARTING_CASH,
        risk_limits: Any = None,
    ):
        self.store_path = Path(store_path)
        self.slippage = slippage
        self.use_sqlite = use_sqlite
        self.starting_cash = float(starting_cash)
        if risk_limits is None:
            try:
                from options_seller.config import load_defaults
                from options_seller.risk.limits import risk_limits_from_config

                risk_limits = risk_limits_from_config(load_defaults())
            except Exception:
                from options_seller.risk.limits import RiskLimits

                risk_limits = RiskLimits()
        self.risk_limits = risk_limits
        self._portfolio: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if self.use_sqlite:
            return _normalize_portfolio(self._load_sqlite())
        if self.store_path.exists():
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
            return _normalize_portfolio(raw)
        return _empty_portfolio(self.starting_cash)

    def _save(self) -> None:
        if self.use_sqlite:
            self._save_sqlite()
            return
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(
            json.dumps(self._portfolio, indent=2), encoding="utf-8"
        )

    def _db_path(self) -> Path:
        return self.store_path.with_suffix(".sqlite3")

    def _load_sqlite(self) -> dict[str, Any]:
        path = self._db_path()
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS fills ("
                "id TEXT PRIMARY KEY, payload TEXT, created_at TEXT)"
            )
            row = conn.execute(
                "SELECT value FROM meta WHERE key='portfolio'"
            ).fetchone()
            if row:
                return json.loads(row[0])
            return _empty_portfolio(self.starting_cash)
        finally:
            conn.close()

    def _save_sqlite(self) -> None:
        path = self._db_path()
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS fills ("
                "id TEXT PRIMARY KEY, payload TEXT, created_at TEXT)"
            )
            payload = json.dumps(self._portfolio)
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('portfolio', ?)",
                (payload,),
            )
            conn.commit()
        finally:
            conn.close()

    def reset(self, starting_cash: float | None = None) -> None:
        cash = float(starting_cash if starting_cash is not None else self.starting_cash)
        self._portfolio = _empty_portfolio(cash)
        self._save()

    def fill_price_for_plan(self, plan: OrderPlan) -> Optional[float]:
        """Net credit (positive) or debit (negative) at mid ± slippage. None for templates."""
        if plan.is_template or plan.net_premium is None:
            return None
        slip = abs(self.slippage)
        if plan.credit_debit == "credit":
            return max(0.0, plan.net_premium * (1.0 - slip))
        return plan.net_premium * (1.0 + slip)

    def _make_position(
        self,
        plan: OrderPlan,
        *,
        fill_price: Optional[float],
        fill_id: Optional[str],
        status: str,
        underlying_price: Optional[float] = None,
        notes: str = "",
    ) -> dict[str, Any]:
        legs = [_leg_dump(leg) for leg in plan.legs]
        credit = fill_price
        # Rough initial mark: for credit trades, mark = remaining liability ~ credit
        # Unrealized starts at 0 (mark equals open credit for short premium)
        mark = credit
        unrealized = 0.0
        return {
            "id": str(uuid.uuid4()),
            "underlying": plan.underlying,
            "strategy": plan.strategy,
            "legs": legs,
            "credit": credit,
            "capital": plan.capital_required,
            "max_profit": plan.max_profit,
            "max_loss": plan.max_loss,
            "opened_at": _utc_now(),
            "status": status,
            "closed_at": None,
            "close_price": None,
            "realized_pnl": None,
            "unrealized_pnl": unrealized,
            "mark": mark,
            "underlying_price_at_open": underlying_price
            or plan.metadata.get("underlying_price"),
            "underlying_mark": underlying_price
            or plan.metadata.get("underlying_price"),
            "dte": plan.target_dte or _dte_from_legs(legs),
            "expiry": plan.metadata.get("expiry"),
            "notes": notes or plan.notes,
            "credit_debit": plan.credit_debit,
            "fill_id": fill_id,
            "is_template": bool(plan.is_template),
            "target_delta": plan.target_delta,
        }

    def execute(self, plan: OrderPlan) -> TradeTicket:
        ticket = plan_to_ticket(plan, slippage=self.slippage)
        if plan.is_template:
            ticket.status = "template_only"
            ticket.fill_price = None
            # Record as planned/template so dashboard can show it
            pos = self._make_position(
                plan,
                fill_price=None,
                fill_id=None,
                status="planned",
                notes=(plan.notes or "") + " [template — no live premium]",
            )
            self._portfolio.setdefault("positions", []).append(pos)
            fill_rec = {
                "id": str(uuid.uuid4()),
                "type": "open_template",
                "strategy": plan.strategy,
                "underlying": plan.underlying,
                "fill_price": None,
                "capital_required": plan.capital_required,
                "max_profit": plan.max_profit,
                "max_loss": plan.max_loss,
                "legs": [_leg_dump(leg) for leg in plan.legs],
                "position_id": pos["id"],
                "ts": _utc_now(),
            }
            self._portfolio.setdefault("fills", []).append(fill_rec)
            pos["fill_id"] = fill_rec["id"]
            self._save()
            return ticket

        from options_seller.risk.limits import can_open, plan_risk

        new_risk = plan_risk(plan)
        allowed, reason = can_open(
            self._portfolio.get("positions", []),
            new_risk,
            self.risk_limits,
        )
        if not allowed:
            ticket.fill_price = None
            ticket.status = "risk_rejected"
            ticket.paper = True
            agg_before = aggregate_open_risk(self._portfolio.get("positions", []))
            cap = float(
                getattr(self.risk_limits, "max_portfolio_risk_usd", DEFAULT_MAX_PORTFOLIO_RISK)
            )
            hr = float(cap) - float(agg_before)
            reject_rec = {
                "id": str(uuid.uuid4()),
                "type": "risk_rejected",
                "strategy": plan.strategy,
                "underlying": plan.underlying,
                "capital_required": plan.capital_required,
                "max_loss": plan.max_loss,
                "proposed_risk": new_risk,
                "aggregate_risk_before": agg_before,
                "max_portfolio_risk_usd": cap,
                "headroom": hr,
                "reason": reason,
                "ts": _utc_now(),
                "fill_price": None,
                "legs": [_leg_dump(leg) for leg in plan.legs],
            }
            self._portfolio.setdefault("fills", []).append(reject_rec)
            self._portfolio.setdefault("risk_events", []).append(dict(reject_rec))
            self._portfolio["last_risk_event"] = dict(reject_rec)
            # Surface reason on ticket via plan notes (TradeTicket has no notes field)
            if plan.notes:
                ticket.plan = plan.model_copy(
                    update={"notes": f"{plan.notes} [{reason}]"}
                )
            else:
                ticket.plan = plan.model_copy(update={"notes": reason})
            self._save()
            return ticket

        fill = self.fill_price_for_plan(plan)
        ticket.fill_price = fill
        ticket.status = "filled_paper"
        ticket.paper = True

        fill_rec = {
            "id": str(uuid.uuid4()),
            "type": "open",
            "strategy": plan.strategy,
            "underlying": plan.underlying,
            "fill_price": fill,
            "capital_required": plan.capital_required,
            "max_profit": plan.max_profit,
            "max_loss": plan.max_loss,
            "legs": [_leg_dump(leg) for leg in plan.legs],
            "ts": _utc_now(),
        }
        self._portfolio.setdefault("fills", []).append(fill_rec)

        if fill is not None and plan.credit_debit == "credit":
            self._portfolio["cash"] = float(self._portfolio.get("cash", 0)) + float(fill)
            self._portfolio["premium_collected_lifetime"] = float(
                self._portfolio.get("premium_collected_lifetime", 0)
            ) + float(fill)
        elif fill is not None and plan.credit_debit == "debit":
            self._portfolio["cash"] = float(self._portfolio.get("cash", 0)) - abs(
                float(fill)
            )

        pos = self._make_position(
            plan,
            fill_price=fill,
            fill_id=fill_rec["id"],
            status="open",
        )
        fill_rec["position_id"] = pos["id"]
        self._portfolio.setdefault("positions", []).append(pos)
        self._save()
        return ticket

    def open_demo_position(
        self,
        *,
        underlying: str,
        strategy: str,
        legs: list[dict[str, Any]],
        credit: float,
        capital: float,
        max_profit: float | None = None,
        max_loss: float | None = None,
        dte: int | None = None,
        underlying_price: float | None = None,
        notes: str = "demo seed",
        mark_fraction: float = 0.55,
    ) -> dict[str, Any]:
        """Open a synthetic filled paper position (for seeding charts)."""
        plan = OrderPlan(
            strategy=strategy,
            underlying=underlying,
            legs=[],  # legs provided as dicts below
            credit_debit="credit",
            net_premium=credit,
            max_profit=max_profit if max_profit is not None else credit,
            max_loss=max_loss,
            capital_required=capital,
            is_template=False,
            target_dte=dte,
            notes=notes,
            metadata={"underlying_price": underlying_price},
        )
        # Bypass OrderPlan leg validation by building position directly
        fill_id = str(uuid.uuid4())
        mark = round(credit * mark_fraction, 2)  # remaining short value
        # For credit sellers: unrealized = credit - mark (profit as mark decays)
        unrealized = round(credit - mark, 2)
        pos = {
            "id": str(uuid.uuid4()),
            "underlying": underlying,
            "strategy": strategy,
            "legs": legs,
            "credit": credit,
            "capital": capital,
            "max_profit": max_profit if max_profit is not None else credit,
            "max_loss": max_loss,
            "opened_at": _utc_now(),
            "status": "open",
            "closed_at": None,
            "close_price": None,
            "realized_pnl": None,
            "unrealized_pnl": unrealized,
            "mark": mark,
            "underlying_price_at_open": underlying_price,
            "underlying_mark": underlying_price,
            "dte": dte or _dte_from_legs(legs),
            "expiry": None,
            "notes": notes,
            "credit_debit": "credit",
            "fill_id": fill_id,
            "is_template": False,
            "target_delta": None,
        }
        fill_rec = {
            "id": fill_id,
            "type": "open",
            "strategy": strategy,
            "underlying": underlying,
            "fill_price": credit,
            "capital_required": capital,
            "max_profit": pos["max_profit"],
            "max_loss": max_loss,
            "legs": legs,
            "position_id": pos["id"],
            "ts": _utc_now(),
            "demo": True,
        }
        self._portfolio.setdefault("fills", []).append(fill_rec)
        self._portfolio["cash"] = float(self._portfolio.get("cash", 0)) + float(credit)
        self._portfolio["premium_collected_lifetime"] = float(
            self._portfolio.get("premium_collected_lifetime", 0)
        ) + float(credit)
        self._portfolio.setdefault("positions", []).append(pos)
        # silence unused
        _ = plan
        self._save()
        return pos

    def update_mark(
        self,
        position_id: str,
        *,
        mark: float | None = None,
        underlying_mark: float | None = None,
        mark_fraction: float | None = None,
    ) -> dict[str, Any]:
        """Update unrealized mark for an open position. EST when no live quotes."""
        pos = self.get_position(position_id)
        if pos is None:
            raise KeyError(f"position not found: {position_id}")
        if pos.get("status") not in ("open", "planned"):
            raise ValueError("can only mark open/planned positions")

        credit = pos.get("credit")
        if mark is None and mark_fraction is not None and credit is not None:
            mark = round(float(credit) * float(mark_fraction), 2)
        if mark is not None:
            pos["mark"] = float(mark)
            pos["marked_at"] = _utc_now()
            if credit is not None and pos.get("credit_debit") == "credit":
                pos["unrealized_pnl"] = round(float(credit) - float(mark), 2)
            elif credit is not None:
                pos["unrealized_pnl"] = round(float(mark) - abs(float(credit)), 2)
        if underlying_mark is not None:
            pos["underlying_mark"] = float(underlying_mark)
        self._save()
        return pos

    def close_position(
        self, position_id: str, price: float | None = None
    ) -> dict[str, Any]:
        """Close an open/planned position; realize PnL and free capital.

        For credit trades, ``price`` is the debit paid to buy back (close cost).
        If omitted, uses current mark, else 50% of credit as EST buyback.
        """
        pos = self.get_position(position_id)
        if pos is None:
            raise KeyError(f"position not found: {position_id}")
        if pos.get("status") not in ("open", "planned"):
            raise ValueError(f"position {position_id} is not open (status={pos.get('status')})")

        credit = pos.get("credit")
        if pos.get("status") == "planned" or credit is None:
            # Template/planned: close with zero PnL
            close_cost = 0.0
            realized = 0.0
        else:
            if price is not None:
                close_cost = float(price)
            elif pos.get("mark") is not None:
                close_cost = float(pos["mark"])
            else:
                close_cost = round(float(credit) * 0.5, 2)

            if pos.get("credit_debit") == "credit":
                realized = round(float(credit) - close_cost, 2)
                # Pay debit to close
                self._portfolio["cash"] = float(self._portfolio.get("cash", 0)) - close_cost
            else:
                # Debit trade: sell to close at price
                realized = round(close_cost - abs(float(credit)), 2)
                self._portfolio["cash"] = float(self._portfolio.get("cash", 0)) + close_cost

        pos["status"] = "closed"
        pos["closed_at"] = _utc_now()
        pos["close_price"] = close_cost if credit is not None else None
        pos["realized_pnl"] = realized
        pos["unrealized_pnl"] = 0.0

        self._portfolio["realized_pnl_lifetime"] = float(
            self._portfolio.get("realized_pnl_lifetime", 0)
        ) + float(realized)

        fill_rec = {
            "id": str(uuid.uuid4()),
            "type": "close",
            "strategy": pos.get("strategy"),
            "underlying": pos.get("underlying"),
            "fill_price": close_cost if credit is not None else None,
            "realized_pnl": realized,
            "position_id": pos["id"],
            "ts": _utc_now(),
        }
        self._portfolio.setdefault("fills", []).append(fill_rec)
        self._save()
        return pos

    def get_position(self, position_id: str) -> Optional[dict[str, Any]]:
        for p in self._portfolio.get("positions", []):
            if p.get("id") == position_id:
                return p
        return None

    def list_open(self) -> list[dict[str, Any]]:
        return [
            p
            for p in self._portfolio.get("positions", [])
            if p.get("status") in ("open", "planned")
        ]

    def list_closed(self) -> list[dict[str, Any]]:
        return [
            p for p in self._portfolio.get("positions", []) if p.get("status") == "closed"
        ]

    def list_fills(self) -> list[dict[str, Any]]:
        fills = list(self._portfolio.get("fills", []))
        fills.sort(key=lambda f: f.get("ts") or "", reverse=True)
        return fills

    @property
    def portfolio(self) -> dict[str, Any]:
        return self._portfolio
