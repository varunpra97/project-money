"""Real brokerage positions: Varun's Robinhood book synced via Plaid.

A scheduled job on the assistant VM pulls holdings through the Plaid
connector (read-only) and POSTs a snapshot here; the iOS app reads the
mapped positions/summary through token-gated endpoints. Nothing here can
trade — it only stores and serves the last synced snapshot.

Auth (tokens live in Render env vars, never in the repo):
  - POST /api/brokerage/sync  ->  X-Sync-Token: BROKERAGE_SYNC_TOKEN
  - GET  /api/brokerage/*      ->  X-App-Token:  APP_READ_TOKEN

State lives in Postgres when DATABASE_URL is set (Neon), else in
data/brokerage_snapshot.json (local dev only — ephemeral on Render).
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger("pulse.brokerage")

_DATA = Path(__file__).resolve().parent / "data"
_SNAP_FILE = _DATA / "brokerage_snapshot.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Tokens ────────────────────────────────────────────────────────────────

def sync_token_ok(provided: str | None) -> bool:
    expected = os.environ.get("BROKERAGE_SYNC_TOKEN")
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided, expected)


def app_token_ok(provided: str | None) -> bool:
    expected = os.environ.get("APP_READ_TOKEN")
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided, expected)


# ── Snapshot store ────────────────────────────────────────────────────────

_db_init_done = False


def _db_configured() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


def _db_connect():
    import psycopg2

    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=10)
    conn.autocommit = True
    return conn


@contextmanager
def _pg():
    conn = _db_connect()
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _db_init(conn) -> None:
    global _db_init_done
    if _db_init_done:
        return
    with conn.cursor() as cur:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS brokerage_snapshot (
                   id INTEGER PRIMARY KEY,
                   payload JSONB NOT NULL,
                   updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
               )"""
        )
    _db_init_done = True


def save_snapshot(payload: dict) -> dict:
    """Map raw Plaid holdings, merge first-seen dates, persist. Returns the
    stored payload summary."""
    holdings = payload.get("holdings") or []
    securities = payload.get("securities") or []
    account = payload.get("account") or {}
    synced_at = payload.get("synced_at") or _now()

    positions = map_positions(holdings, securities)

    prev = load_snapshot() or {}
    prev_seen = prev.get("first_seen") or {}
    first_seen = dict(prev_seen)
    for p in positions:
        pid = p.get("id")
        if pid and pid not in first_seen:
            first_seen[pid] = synced_at

    stored = {
        "account": account,
        "holdings": holdings,
        "securities": securities,
        "positions": positions,
        "summary": summary_payload(account, holdings, securities, positions, synced_at),
        "first_seen": first_seen,
        "synced_at": synced_at,
    }
    # Stamp first-seen (tracked-since) onto positions for the "Opened" row.
    for p in stored["positions"]:
        p["opened_at"] = first_seen.get(p.get("id"), synced_at)

    blob = json.dumps(stored)
    if _db_configured():
        with _pg() as conn:
            _db_init(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO brokerage_snapshot (id, payload, updated_at)
                       VALUES (1, %s::jsonb, NOW())
                       ON CONFLICT (id) DO UPDATE
                       SET payload = EXCLUDED.payload, updated_at = NOW()""",
                    (blob,),
                )
    else:
        _DATA.mkdir(parents=True, exist_ok=True)
        tmp = _SNAP_FILE.with_suffix(".tmp")
        tmp.write_text(blob)
        tmp.replace(_SNAP_FILE)
    log.info("brokerage: snapshot saved (%d positions)", len(positions))
    return {"ok": True, "positions": len(positions),
            "holdings": len(holdings), "synced_at": synced_at}


def load_snapshot() -> dict | None:
    if _db_configured():
        try:
            with _pg() as conn:
                _db_init(conn)
                with conn.cursor() as cur:
                    cur.execute("SELECT payload FROM brokerage_snapshot WHERE id = 1")
                    row = cur.fetchone()
                    if row and row[0]:
                        p = row[0]
                        return p if isinstance(p, dict) else json.loads(p)
        except Exception:
            log.warning("brokerage: snapshot read failed", exc_info=True)
        return None
    if _SNAP_FILE.exists():
        try:
            return json.loads(_SNAP_FILE.read_text())
        except Exception:
            return None
    return None


# ── Mapping: Plaid holdings -> app position rows ───────────────────────────

_STRATEGY_NAMES = {
    "put_credit_spread": "Put Credit Spread",
    "put_debit_spread": "Put Debit Spread",
    "call_credit_spread": "Call Credit Spread",
    "call_debit_spread": "Call Debit Spread",
    "long_call": "Long Call",
    "long_put": "Long Put",
    "short_call": "Short Call",
    "short_put": "Short Put",
    "custom_spread": "Custom Spread",
    "shares": "Shares",
}


def _dte(expiry: str | None) -> int | None:
    if not expiry:
        return None
    try:
        return max((date.fromisoformat(expiry) - date.today()).days, 0)
    except ValueError:
        return None


def _sec_by_id(securities) -> dict:
    return {s.get("security_id"): s for s in securities or []}


def map_positions(holdings, securities) -> list[dict]:
    secs = _sec_by_id(securities)
    groups: dict[tuple[str, str], list] = {}
    equities: list[tuple[dict, dict]] = []
    for h in holdings or []:
        s = secs.get(h.get("security_id")) or {}
        stype = s.get("type")
        if stype == "derivative":
            oc = s.get("option_contract") or {}
            und = str(oc.get("underlying_security_ticker") or "").upper()
            exp = str(oc.get("expiration_date") or "")
            if not und:
                continue
            groups.setdefault((und, exp), []).append((h, s))
        elif stype in ("equity", "etf"):
            equities.append((h, s))
        # cash / currency holdings are not positions
    out: list[dict] = []
    for (und, exp), legs in sorted(groups.items()):
        out.append(_map_option_group(und, exp, legs))
    for h, s in equities:
        out.append(_map_equity(h, s))
    return out


def _map_option_group(underlying: str, expiry: str, legs: list) -> dict:
    items = []
    for h, s in legs:
        oc = s.get("option_contract") or {}
        qty = float(h.get("quantity") or 0)
        items.append({
            "side": "buy" if qty > 0 else "sell",
            "option_type": str(oc.get("contract_type") or "").lower(),
            "strike": float(oc.get("strike_price") or 0),
            "quantity": abs(qty),
            "expiry": expiry,
            "_signed": qty,
            "_value": float(h.get("institution_value") or 0),
            "_asof": h.get("institution_price_as_of"),
        })
    items.sort(key=lambda l: l["strike"])
    net_qty = sum(i["_signed"] for i in items)
    value = sum(i["_value"] for i in items)
    asofs = sorted({str(i["_asof"]) for i in items if i["_asof"]})
    n = len(items)

    if (n == 2 and items[0]["option_type"] == items[1]["option_type"]
            and items[0]["option_type"] in ("call", "put")):
        otype = items[0]["option_type"]
        lo, hi = items[0], items[1]
        width = hi["strike"] - lo["strike"]
        if otype == "put":
            credit = hi["_signed"] < 0 < lo["_signed"]
            strategy = "put_credit_spread" if credit else "put_debit_spread"
        else:
            credit = lo["_signed"] < 0 < hi["_signed"]
            strategy = "call_credit_spread" if credit else "call_debit_spread"
        contracts = abs(lo["_signed"])
        max_loss = round(width * 100 * contracts, 2) if width > 0 else None
    elif n == 1:
        it = items[0]
        long = it["_signed"] > 0
        otype = it["option_type"] if it["option_type"] in ("call", "put") else "call"
        strategy = ("long_" if long else "short_") + otype
        # Long premium: the most you can lose from here is what it's worth.
        # Short premium without a hedge: undefined.
        max_loss = round(abs(value), 2) if long else None
        contracts = abs(it["_signed"])
    else:
        strategy = "custom_spread"
        max_loss = None
        contracts = sum(abs(i["_signed"]) for i in items)

    legs_out = [{k: i[k] for k in ("side", "option_type", "strike", "quantity", "expiry")}
                for i in items]
    return {
        "id": f"rh-{underlying}-{expiry}",
        "underlying": underlying,
        "strategy": strategy,
        "display_name": f"{underlying} {_STRATEGY_NAMES[strategy]}",
        "opened_at": None,  # stamped with first-seen on save
        "dte": _dte(expiry),
        "expiry": expiry,
        "opening_value": None,   # entry premium is not reported by Plaid
        "close_value": round(abs(value), 2),
        "premium_direction": "credit" if net_qty < 0 else "debit",
        "mark_as_of": asofs[-1] if asofs else None,
        "day_pnl": None,
        "return_pct": None,
        "equity": round(value, 2),
        "legs": legs_out,
        "qty": contracts,
        "credit": None,
        "unrealized": None,
        "pct_of_max_profit": None,
        "days_held": None,
        "risk_label": None,
        "max_loss": max_loss,
        "max_profit": None,
    }


def _map_equity(h: dict, s: dict) -> dict:
    ticker = str(s.get("ticker_symbol") or "").upper()
    qty = float(h.get("quantity") or 0)
    value = float(h.get("institution_value") or 0)
    asof = h.get("institution_price_as_of")
    return {
        "id": f"rh-{ticker}",
        "underlying": ticker,
        "strategy": "shares",
        "display_name": f"{ticker} Shares",
        "opened_at": None,
        "dte": None,
        "expiry": None,
        "opening_value": None,
        "close_value": round(abs(value), 2),
        "premium_direction": "debit",
        "mark_as_of": str(asof) if asof else None,
        "day_pnl": None,
        "return_pct": None,
        "equity": round(value, 2),
        "legs": [],
        "qty": qty,
        "credit": None,
        "unrealized": None,
        "pct_of_max_profit": None,
        "days_held": None,
        "risk_label": None,
        "max_loss": round(abs(value), 2),  # shares can't lose more than they're worth
        "max_profit": None,
    }


def summary_payload(account: dict, holdings, securities, positions, synced_at: str) -> dict:
    balances = (account or {}).get("balances") or {}
    secs = _sec_by_id(securities)
    cash = 0.0
    for h in holdings or []:
        s = secs.get(h.get("security_id")) or {}
        if s.get("type") == "cash":
            try:
                cash += float(h.get("quantity") or 0)
            except (TypeError, ValueError):
                pass
    try:
        account_value = float(balances.get("current") or 0)
    except (TypeError, ValueError):
        account_value = 0.0
    try:
        buying_power = float(balances.get("available") or 0)
    except (TypeError, ValueError):
        buying_power = 0.0
    return {
        "account_value": round(account_value, 2),
        "buying_power": round(buying_power, 2),
        "cash": round(cash, 2),
        "day_pnl": 0.0,
        "day_pnl_pct": 0.0,
        "total_pnl": 0.0,
        "open_positions": len(positions),
        "greeks": None,
        "as_of": synced_at,
    }
