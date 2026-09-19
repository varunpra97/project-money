"""Paper performance from recorded trades and observed P&L, never invented history."""
from datetime import datetime, timedelta, timezone
import json
import threading
from pathlib import Path
from options_seller.portfolio.api import load_executor, summary_metrics

LOCK = threading.Lock()
HISTORY = Path(__file__).resolve().parents[1] / "data" / "performance_history.json"


def stamp(value):
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def performance(period="lifetime", executor=None, now=None, history_path=None):
    now = now or datetime.now(timezone.utc)
    ex = executor or load_executor()
    m = summary_metrics(ex)
    pf = ex.portfolio
    total = round(m["realized_pnl"] + m["unrealized_pnl"], 2)
    path = Path(history_path or HISTORY)
    # Detect reset/replacement, including a reset to another portfolio of the same size.
    identity = sorted((str(p.get("id")), str(p.get("opened_at"))) for p in pf.get("positions", []))
    with LOCK:
        history = json.loads(path.read_text()) if path.exists() else {"samples": [], "identity": []}
        previous_ids = {tuple(x) for x in history.get("identity", [])}
        if previous_ids and not previous_ids.issubset(set(identity)):
            history = {"samples": [], "identity": []}
        history["identity"] = identity
        samples = history["samples"]
        point = {"ts": now.isoformat(), "pnl": total}
        if not samples or (now - stamp(samples[-1]["ts"])).total_seconds() >= 60:
            samples.append(point)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(history))
        tmp.replace(path)
    days = {"week": 7, "month": 30, "quarter": 90}.get(period)
    since = now - timedelta(days=days) if days else None
    def included(date):
        d = stamp(date)
        return d is not None and d <= now and (since is None or d >= since)
    closed = [p for p in ex.list_closed() if p.get("realized_pnl") is not None and included(p.get("closed_at"))]
    values = [float(p["realized_pnl"]) for p in closed]
    realized = m["realized_pnl"] if since is None else round(sum(values), 2)
    before = [s for s in samples if since and stamp(s["ts"]) <= since]
    baseline = before[-1] if before else None
    # Require a recent opening observation rather than pretending a long data gap is complete.
    covered = baseline is not None and (since - stamp(baseline["ts"])).total_seconds() <= 86400
    pnl = total if since is None else round(total-baseline["pnl"], 2) if covered else None
    curve = [s for s in samples if since is None or stamp(s["ts"]) >= since]
    if covered:
        curve = [baseline] + curve
    curve = [{"ts": s["ts"], "pnl": round(s["pnl"] - (baseline["pnl"] if covered else 0), 2)} for s in curve]
    strategies = {}
    for p in closed:
        key = p.get("strategy") or "unknown"
        item = strategies.setdefault(key, {"strategy": key.replace("_", " ").title(), "trades": 0, "realized": 0.0})
        item["trades"] += 1
        item["realized"] = round(item["realized"] + float(p["realized_pnl"]), 2)
    wins = [v for v in values if v > 0]
    losses = [v for v in values if v < 0]
    record_realized = sum(float(p.get("realized_pnl") or 0) for p in ex.list_closed())
    notes = ["Paper portfolio. P&L uses saved marks, not live option quotes. Week / month / quarter mean trailing 7 / 30 / 90 days in UTC."]
    if any(f.get("demo") for f in pf.get("fills", [])):
        notes.append("This book contains demo trades and synthetic marks.")
    if abs(record_realized-m["realized_pnl"]) > .01:
        notes.append("Lifetime realized P&L includes a carried balance without matching closed-trade records; dated trade statistics exclude that balance.")
    if since and not covered:
        notes.append("Total period P&L is unavailable until an opening snapshot exists. Closed-trade P&L below includes only recorded closes in this window.")
    return {
        "period": period, "as_of": now.isoformat(), "since": since.isoformat() if since else None,
        "pnl": pnl, "realized": realized, "unrealized": m["unrealized_pnl"],
        "closed_trades": len(values), "win_rate": round(len(wins)/len(values)*100, 1) if values else None,
        "average_win": round(sum(wins)/len(wins), 2) if wins else None,
        "average_loss": round(sum(losses)/len(losses), 2) if losses else None,
        "best_trade": max(values) if values else None, "worst_trade": min(values) if values else None,
        "profit_factor": round(sum(wins)/abs(sum(losses)), 2) if losses else None,
        "open_positions": m["open_positions"], "premium": m["premium_collected"] if since is None else round(sum(float(f.get("fill_price") or 0) for f in pf.get("fills", []) if f.get("type") == "open" and included(f.get("ts"))), 2),
        "history_since": samples[0]["ts"], "curve": curve, "curve_label": "Observed period P&L" if covered else "Observed lifetime P&L",
        "strategies": list(strategies.values()), "notes": notes,
    }
