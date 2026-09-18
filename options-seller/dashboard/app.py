"""Options Seller Command Center — paper-trading dashboard (NOT LIVE).

Mimics tastytrade / thinkorswim Analyze / OptionTracker-style UX.
Never contacts a live broker.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Ensure src is importable when launched via `streamlit run dashboard/app.py`
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from options_seller.config import load_defaults
from options_seller.execution.paper import PaperExecutor
from options_seller.models.orders import OrderPlan
from options_seller.models.scanner import PortfolioContext
from options_seller.portfolio.api import (
    DEFAULT_PAPER_PATH,
    days_held,
    pct_of_max_profit,
    portfolio_greeks_est,
    seed_demo_book,
    strategies_in_play,
    strategy_performance,
    summary_metrics,
    ticker_performance,
)
from options_seller.portfolio.celebrity_priority import celebrity_overlay, rollup_ticker
from options_seller.portfolio.payoff import payoff_series
from options_seller.risk import (
    enforce_hard_limits,
    evaluate_book,
    risk_limits_from_config,
)
from options_seller.portfolio.scanner_feed import (
    build_candidates,
    load_scan_envelope,
    refresh_scan_data,
    scanner_base_url,
    scanner_json_path,
    scanner_ui_url,
)

st.set_page_config(
    page_title="Options Seller — Command Center",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Dark finance theme (match stock-data-scanner)
st.markdown(
    """
<style>
    .stApp { background-color: #0b0f14; color: #e6edf3; }
    [data-testid="stSidebar"] { background-color: #111821; }
    h1, h2, h3 { color: #e6edf3 !important; }
    .up { color: #3dd68c; font-weight: 600; }
    .down { color: #f85149; font-weight: 600; }
    .amber { color: #c9a227; font-weight: 600; }
    .metric-card {
        background: #151c25; border: 1px solid #243041; border-radius: 10px;
        padding: 0.75rem 0.9rem; margin-bottom: 0.35rem; min-height: 4.5rem;
    }
    .metric-label { color: #9aa8bc; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.04em; }
    .metric-value { font-size: 1.05rem; font-weight: 600; margin-top: 0.2rem; }
    .paper-banner {
        background: linear-gradient(90deg, #3d1f00, #5a2d00);
        border: 1px solid #c47a00; color: #ffcc66;
        padding: 0.55rem 1rem; border-radius: 8px; font-weight: 700;
        text-align: center; margin-bottom: 0.5rem; letter-spacing: 0.06em;
    }
    .flash-ok {
        background: #0d2818; border: 1px solid #3dd68c; color: #3dd68c;
        padding: 0.55rem 1rem; border-radius: 8px; margin-bottom: 0.6rem;
        display: flex; justify-content: space-between; align-items: center; gap: 1rem;
    }
    .flash-bad {
        background: #2a1215; border: 1px solid #f85149; color: #f85149;
        padding: 0.55rem 1rem; border-radius: 8px; margin-bottom: 0.6rem;
        display: flex; justify-content: space-between; align-items: center; gap: 1rem;
    }
    .flash-amber {
        background: #2a2208; border: 1px solid #c9a227; color: #e6c35c;
        padding: 0.55rem 1rem; border-radius: 8px; margin-bottom: 0.6rem;
        display: flex; justify-content: space-between; align-items: center; gap: 1rem;
    }
    .greeks-bar {
        background: #151c25; border: 1px solid #243041; border-radius: 10px;
        padding: 0.65rem 1rem; display: flex; gap: 1.5rem; flex-wrap: wrap;
        align-items: center; margin: 0.5rem 0 0.75rem 0;
    }
    .greek-item { font-size: 0.95rem; }
    .greek-label { color: #9aa8bc; font-size: 0.7rem; text-transform: uppercase; }
    .est-tag { color: #c9a227; font-size: 0.65rem; font-weight: 700; margin-left: 0.25rem; }
    .status-ok { color: #3dd68c; }
    .status-bad { color: #f85149; }
    .status-warn { color: #c9a227; }
    .strat-card {
        background: #151c25; border: 1px solid #243041; border-radius: 10px;
        padding: 0.65rem 0.85rem; margin-bottom: 0.4rem; cursor: default;
        min-height: 5.2rem;
    }
    .strat-card.active { border-color: #58a6ff; box-shadow: 0 0 0 1px #58a6ff55; }
    .strat-name { font-weight: 700; font-size: 0.95rem; margin-bottom: 0.25rem; }
    .strat-meta { color: #9aa8bc; font-size: 0.75rem; }
    .pos-header { font-size: 1.05rem; font-weight: 700; }
    .badge-priority {
        background: #3d2a00; color: #ffcc66; border: 1px solid #c47a00;
        border-radius: 4px; padding: 0.1rem 0.4rem; font-size: 0.7rem; font-weight: 700;
        margin-left: 0.35rem;
    }
    .caution-cap { color: #c9a227; font-size: 0.72rem; margin-top: 0.15rem; }
    div[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }

    /* --- Dark theme controls (buttons / inputs / tabs) --- */
    .greek-label, .strat-meta { color: #9aa8bc; }

    /* Secondary / default buttons */
    div[data-testid="stButton"] > button[kind="secondary"],
    div[data-testid="stButton"] > button:not([kind="primary"]),
    button[data-testid="baseButton-secondary"],
    .stButton > button {
        background-color: #1c2430 !important;
        color: #e6edf3 !important;
        border: 1px solid #30363d !important;
        border-radius: 6px !important;
    }
    div[data-testid="stButton"] > button[kind="secondary"]:hover,
    div[data-testid="stButton"] > button:not([kind="primary"]):hover,
    button[data-testid="baseButton-secondary"]:hover,
    .stButton > button:hover {
        background-color: #21262d !important;
        border-color: #484f58 !important;
        color: #f0f6fc !important;
    }

    /* Primary buttons */
    div[data-testid="stButton"] > button[kind="primary"],
    button[data-testid="baseButton-primary"] {
        background-color: #238636 !important;
        color: #ffffff !important;
        border: 1px solid #2ea043 !important;
        border-radius: 6px !important;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover,
    button[data-testid="baseButton-primary"]:hover {
        background-color: #2ea043 !important;
        border-color: #3fb950 !important;
        color: #ffffff !important;
    }

    /* Link buttons — blue outline, not white fill */
    div[data-testid="stLinkButton"] > a,
    a[data-testid="baseLinkButton-secondary"],
    a[data-testid="stBaseLinkButton-secondary"] {
        background-color: #1c2430 !important;
        color: #58a6ff !important;
        border: 1px solid #30363d !important;
        border-radius: 6px !important;
    }
    div[data-testid="stLinkButton"] > a:hover,
    a[data-testid="baseLinkButton-secondary"]:hover,
    a[data-testid="stBaseLinkButton-secondary"]:hover {
        background-color: #21262d !important;
        border-color: #58a6ff !important;
        color: #79b8ff !important;
    }

    /* Text / number / text-area inputs */
    div[data-testid="stTextInput"] input,
    div[data-testid="stNumberInput"] input,
    div[data-testid="stTextArea"] textarea,
    .stTextInput input, .stNumberInput input, .stTextArea textarea {
        background-color: #0d1117 !important;
        color: #e6edf3 !important;
        border: 1px solid #30363d !important;
        border-radius: 6px !important;
    }
    div[data-testid="stTextInput"] input::placeholder,
    div[data-testid="stTextArea"] textarea::placeholder {
        color: #8b9bb4 !important;
        opacity: 1 !important;
    }

    /* Selectboxes / multiselect */
    div[data-testid="stSelectbox"] > div > div,
    div[data-testid="stMultiSelect"] > div > div,
    [data-baseweb="select"] > div {
        background-color: #0d1117 !important;
        color: #e6edf3 !important;
        border-color: #30363d !important;
    }
    [data-baseweb="popover"] ul,
    [data-baseweb="menu"] {
        background-color: #151c25 !important;
        color: #e6edf3 !important;
        border: 1px solid #30363d !important;
    }
    [data-baseweb="menu"] li:hover,
    [role="option"]:hover {
        background-color: #21262d !important;
    }

    /* Tabs — clear active vs inactive on dark */
    button[data-baseweb="tab"] {
        color: #8b9bb4 !important;
        background: transparent !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #e6edf3 !important;
        border-bottom-color: #58a6ff !important;
    }
    button[data-baseweb="tab"]:hover {
        color: #e6edf3 !important;
    }
    /* Streamlit/BaseWeb tabs: force the active accent over theme defaults. */
    :root,
    .stApp {
        --primary-color: #58a6ff !important;
    }
    div[data-testid="stTabs"] [data-baseweb="tab-highlight"],
    div[data-testid="stTabs"] [data-baseweb="tab-border"] {
        background-color: #58a6ff !important;
        border-color: #58a6ff !important;
    }
    div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"],
    div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"]::after {
        border-bottom-color: #58a6ff !important;
        box-shadow: inset 0 -2px 0 #58a6ff !important;
    }

    /* Sidebar readability */
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stMarkdown,
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
        color: #c9d1d9 !important;
    }
    [data-testid="stSidebar"] .stCaption, [data-testid="stSidebar"] small {
        color: #9aa8bc !important;
    }

    /* Dataframe / expander headers on dark */
    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] details summary,
    .streamlit-expanderHeader {
        color: #e6edf3 !important;
        background-color: #151c25 !important;
    }
    /* Dataframes / glide-data-grid wrappers: keep the table dark without
       changing the component's scrolling/resize behavior. */
    div[data-testid="stDataFrame"],
    div[data-testid="stDataFrame"] > div,
    div[data-testid="stDataFrame"] [data-testid="stDataFrameResizable"],
    div[data-testid="stDataFrame"] [class*="glide"],
    div[data-testid="stDataFrame"] [class*="Grid"],
    div[data-testid="stDataFrame"] [class*="grid"] {
        background-color: #151c25 !important;
        color: #e6edf3 !important;
    }
    div[data-testid="stDataFrame"] canvas {
        background-color: #151c25 !important;
    }
    div[data-testid="stDataFrame"] [role="grid"],
    div[data-testid="stDataFrame"] [role="row"],
    div[data-testid="stDataFrame"] [role="gridcell"] {
        background-color: #151c25 !important;
        color: #e6edf3 !important;
    }

    /* Danger: Reset paper book (keyed button) */
    div[class*="st-key-reset_paper_book"] button,
    .st-key-reset_paper_book button {
        background-color: #3d1215 !important;
        color: #ffa198 !important;
        border: 1px solid #f85149 !important;
    }
    div[class*="st-key-reset_paper_book"] button:hover,
    .st-key-reset_paper_book button:hover {
        background-color: #da3633 !important;
        color: #ffffff !important;
        border-color: #f85149 !important;
    }

</style>
""",
    unsafe_allow_html=True,
)


# ── Session defaults ─────────────────────────────────────────────────────
def _ensure_session() -> None:
    st.session_state.setdefault("portfolio_path", str(DEFAULT_PAPER_PATH))
    st.session_state.setdefault("slippage", 0.02)
    st.session_state.setdefault(
        "capital_ctx_path",
        str(_ROOT / "examples" / "portfolio.json"),
    )
    st.session_state.setdefault("last_action", None)
    st.session_state.setdefault("strategy_filter", None)
    st.session_state.setdefault("focus_position_id", None)
    st.session_state.setdefault("positions_subtab", "Open")


def _set_last_action(
    kind: str,
    message: str,
    *,
    pnl: float | None = None,
    position_id: str | None = None,
) -> None:
    st.session_state["last_action"] = {
        "kind": kind,  # ok | bad | amber
        "message": message,
        "pnl": pnl,
        "ts": datetime.now(timezone.utc).isoformat(),
        "position_id": position_id,
    }


def _money(v: Any, signed: bool = False) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    try:
        x = float(v)
        if signed:
            return f"${x:+,.2f}"
        return f"${x:,.2f}"
    except (TypeError, ValueError):
        return "—"


def _pnl_class(v: Any) -> str:
    try:
        if v is None:
            return ""
        return "up" if float(v) >= 0 else "down"
    except (TypeError, ValueError):
        return ""


def _metric_card(label: str, value: str, css_class: str = "", hint: str = "") -> str:
    hint_html = (
        f'<div style="color:#8b9bb4;font-size:0.65rem;margin-top:0.15rem">{hint}</div>'
        if hint
        else ""
    )
    return (
        f'<div class="metric-card"><div class="metric-label">{label}</div>'
        f'<div class="metric-value {css_class}">{value}</div>{hint_html}</div>'
    )


def _legs_summary(legs: list[dict]) -> str:
    parts = []
    for leg in legs or []:
        side = (leg.get("side") or "?")[0].upper()
        ot = (leg.get("option_type") or "?")[0].upper()
        k = leg.get("strike")
        k_s = f"{k:g}" if k is not None else "?"
        qty = int(leg.get("quantity") or 1)
        q = f"×{qty}" if qty != 1 else ""
        parts.append(f"{side}{ot}{k_s}{q}")
    return " / ".join(parts) if parts else "—"


def _contract_qty(legs: list[dict]) -> int:
    """Max leg quantity (short premium contracts for the ticket)."""
    qs = [int(leg.get("quantity") or 1) for leg in (legs or [])]
    return max(qs) if qs else 1


def _strikes_str(legs: list[dict]) -> str:
    ks = [leg.get("strike") for leg in (legs or []) if leg.get("strike") is not None]
    return ", ".join(f"{k:g}" for k in ks) if ks else "—"


def _breakevens_for(pos: dict) -> list[float]:
    try:
        series = payoff_series(pos)
        return list(series.get("breakevens") or [])
    except Exception:
        return []


def _est_realized_on_close(pos: dict, close_debit: float | None) -> float | None:
    """EST realized if closing a credit trade at total ticket debit `$`."""
    credit = pos.get("credit")
    if credit is None:
        return 0.0 if pos.get("status") == "planned" else None
    if pos.get("credit_debit") == "credit":
        if close_debit is None:
            if pos.get("mark") is not None:
                close_debit = float(pos["mark"])
            else:
                close_debit = float(credit) * 0.5
        return round(float(credit) - float(close_debit), 2)
    # debit trade: sell to close
    if close_debit is None:
        close_debit = float(pos.get("mark") or credit)
    return round(float(close_debit) - abs(float(credit)), 2)


def _format_ts_pt(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        ts = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        # America/Los_Angeles ≈ UTC-7 (PDT) for display; label PT
        from zoneinfo import ZoneInfo

        local = ts.astimezone(ZoneInfo("America/Los_Angeles"))
        return local.strftime("%Y-%m-%d %H:%M PT")
    except Exception:
        return str(iso)[:19]


def get_executor() -> PaperExecutor:
    store = Path(st.session_state.get("portfolio_path", str(DEFAULT_PAPER_PATH)))
    slip = float(st.session_state.get("slippage", 0.02))
    return PaperExecutor(store_path=store, slippage=slip)


def load_portfolio_ctx(path_str: str) -> PortfolioContext:
    p = Path(path_str)
    if p.exists():
        try:
            return PortfolioContext.model_validate(
                json.loads(p.read_text(encoding="utf-8"))
            )
        except Exception:
            pass
    return PortfolioContext()


_ensure_session()

# ── Sidebar ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Controls")
    st.caption("PAPER / DRY-RUN ONLY")

    ui_url = scanner_ui_url()
    if ui_url:
        # Label includes host so a stale client session can't hide a dead link
        host = ui_url.split("//", 1)[-1].split("/", 1)[0]
        st.link_button(f"📈 Open Stock Scanner ({host})", ui_url, use_container_width=True)
        st.caption(f"Scanner UI: `{ui_url}`")
        if "len-where-elder" in ui_url:
            st.error("Stale scanner URL detected — restart the Command Center process.")
    else:
        st.warning(
            "Stock Scanner public link is offline. "
            "Scan data still loads from the local file; waiting on a fresh tunnel URL."
        )
        st.caption("Set SCANNER_UI_URL when Stock Data Scanner publishes a new base.")

    if st.button("🔄 Refresh scan data", use_container_width=True):
        # Fast path: poll /api/scan or re-read local JSON — never Yahoo / full recompute
        _env, _status, _meta = refresh_scan_data()
        ms = int(_meta.get("elapsed_ms") or 0)
        mode = _meta.get("mode") or "?"
        if _env is not None:
            _set_last_action(
                "ok",
                f"Scan refreshed in {ms}ms ({mode}) · asOf={_status.get('as_of')} · n={_status.get('n_results')}",
            )
        else:
            _set_last_action("bad", f"Scan refresh failed in {ms}ms — {_status.get('error')}")
        st.session_state["scan_refresh_meta"] = _meta
        # Do NOT clear all Streamlit caches — that forced a heavy cold rerun (~60s settle)
        st.rerun()

    st.text_input("Paper portfolio path", key="portfolio_path")
    st.number_input(
        "Slippage (fraction)",
        min_value=0.0,
        max_value=0.25,
        step=0.01,
        key="slippage",
        format="%.2f",
    )
    st.text_input("Capital context JSON", key="capital_ctx_path")

    st.divider()
    st.markdown("**Open paths (paper)**")
    st.caption(
        "• **Candidates → Open this trade** — opens one selected row.\n"
        "• **Bulk scan → paper open** — walks all scan candidates (dry-run)."
    )
    if st.button("🌱 Seed demo book", use_container_width=True, type="primary"):
        ex = get_executor()
        seeded = seed_demo_book(ex, reset=True)
        _set_last_action(
            "ok",
            f"Demo book seeded — {len(seeded)} open + closed winner",
            position_id=seeded[0]["id"] if seeded else None,
        )
        if seeded:
            st.session_state["focus_position_id"] = seeded[0]["id"]
        st.rerun()

    if st.button("▶ Bulk scan → paper open (all candidates)", use_container_width=True):
        envelope, status = load_scan_envelope()
        if envelope is None:
            _set_last_action("bad", status.get("error") or "No scan data")
        else:
            ex = get_executor()
            ctx = load_portfolio_ctx(st.session_state.capital_ctx_path)
            cfg = load_defaults()
            n_open = n_plan = n_rej = 0
            last_id = None
            for row in build_candidates(envelope, portfolio=ctx, cfg=cfg):
                plan: Optional[OrderPlan] = row.get("plan")
                if plan is None:
                    continue
                ticket = ex.execute(plan)
                if ticket.status == "filled_paper":
                    n_open += 1
                    # find newest open for this underlying
                    for p in reversed(ex.list_open()):
                        if p.get("underlying") == plan.underlying and p.get("status") == "open":
                            last_id = p["id"]
                            break
                elif ticket.status == "template_only":
                    n_plan += 1
                elif ticket.status == "risk_rejected":
                    n_rej += 1
            kind = "ok" if n_open else ("amber" if n_plan else "bad")
            _set_last_action(
                kind,
                f"Bulk dry-run: {n_open} filled, {n_plan} templates, {n_rej} risk-rejected",
                position_id=last_id,
            )
            if last_id:
                st.session_state["focus_position_id"] = last_id
        st.rerun()

    if st.button("🗑 Reset paper book", use_container_width=True, key="reset_paper_book"):
        get_executor().reset()
        _set_last_action("amber", "Paper book reset")
        st.session_state["focus_position_id"] = None
        st.session_state["strategy_filter"] = None
        st.rerun()

    st.divider()
    st.markdown("**Scanner connection**")
    st.code(
        f"BASE={scanner_base_url()}\n"
        f"JSON_PATH={scanner_json_path()}\n"
        f"UI={scanner_ui_url()}\n"
        f"(on-box: local file primary; remote IPv4 best-effort)",
        language="text",
    )


# ── Header banner ────────────────────────────────────────────────────────
st.markdown(
    '<div class="paper-banner">⚠ PAPER TRADING / NOT LIVE — no broker orders</div>',
    unsafe_allow_html=True,
)

# A. Last-action flash strip
_la = st.session_state.get("last_action")
if _la:
    kind = _la.get("kind") or "ok"
    css = {"ok": "flash-ok", "bad": "flash-bad", "amber": "flash-amber"}.get(kind, "flash-ok")
    pnl_bit = ""
    if _la.get("pnl") is not None:
        pnl_bit = f" · <b>{_money(_la['pnl'], signed=True)}</b>"
    ts_bit = _format_ts_pt(_la.get("ts"))
    c_flash, c_x = st.columns([12, 1])
    with c_flash:
        st.markdown(
            f'<div class="{css}"><span>{_la.get("message", "")}{pnl_bit}'
            f' <span style="opacity:0.7;font-size:0.8rem">({ts_bit})</span></span></div>',
            unsafe_allow_html=True,
        )
    with c_x:
        if st.button("✕", key="dismiss_last_action", help="Dismiss"):
            st.session_state["last_action"] = None
            st.rerun()

st.title("Options Seller — Command Center")
st.caption(
    "Multi-leg credit strategies · Positions · Risk · Performance · Candidates from scanner"
)

# Main-page toolbar — always visible (probes fail when sidebar is collapsed)
_tb1, _tb2, _tb3, _tb4 = st.columns([1.15, 1.15, 1.15, 2.5])
with _tb1:
    if st.button("Refresh scan data", key="toolbar_refresh_scan", use_container_width=True):
        _env, _status, _meta = refresh_scan_data()
        ms = int(_meta.get("elapsed_ms") or 0)
        mode = _meta.get("mode") or "?"
        if _env is not None:
            _set_last_action(
                "ok",
                f"Scan refreshed in {ms}ms ({mode}) · asOf={_status.get('as_of')} · n={_status.get('n_results')}",
            )
        else:
            _set_last_action(
                "bad",
                f"Scan refresh failed in {ms}ms — {_status.get('error')}",
            )
        st.session_state["scan_refresh_meta"] = _meta
        st.rerun()
with _tb2:
    if st.button("Seed demo book", key="toolbar_seed_demo", type="primary", use_container_width=True):
        ex = get_executor()
        seeded = seed_demo_book(ex, reset=True)
        _set_last_action(
            "ok",
            f"Demo book seeded — {len(seeded)} open + closed winner",
            position_id=seeded[0]["id"] if seeded else None,
        )
        if seeded:
            st.session_state["focus_position_id"] = seeded[0]["id"]
        st.rerun()
with _tb3:
    _ui = scanner_ui_url()
    if _ui:
        st.link_button("Open Stock Scanner", _ui, use_container_width=True)
with _tb4:
    st.caption("Toolbar always visible. Refresh polls /api/scan only (not Yahoo).")


ex = get_executor()
metrics = summary_metrics(ex)
greeks = portfolio_greeks_est(ex)

# Account header cards
c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
with c1:
    st.markdown(
        _metric_card(
            "Net Liq / Cash",
            f"{_money(metrics['net_liquidation'])} / {_money(metrics['cash'])}",
        ),
        unsafe_allow_html=True,
    )
with c2:
    st.markdown(
        _metric_card(
            "Day P&L (EST)",
            _money(metrics["day_pnl"], signed=True),
            _pnl_class(metrics["day_pnl"]),
            hint="Realized closed today + open unrealized — not a broker day P&L",
        ),
        unsafe_allow_html=True,
    )
with c3:
    st.markdown(
        _metric_card(
            "Unrealized P&L",
            _money(metrics["unrealized_pnl"], signed=True),
            _pnl_class(metrics["unrealized_pnl"]),
            hint="Open marks vs credit (EST)",
        ),
        unsafe_allow_html=True,
    )
with c4:
    st.markdown(
        _metric_card(
            "Realized P&L",
            _money(metrics["realized_pnl"], signed=True),
            _pnl_class(metrics["realized_pnl"]),
            hint="Closed trades only (credit − buyback)",
        ),
        unsafe_allow_html=True,
    )
with c5:
    st.markdown(
        _metric_card(
            "Premium Collected",
            _money(metrics["premium_collected"]),
            hint="Sum of credits when opened — not the same as realized",
        ),
        unsafe_allow_html=True,
    )
with c6:
    n_open = metrics["open_positions"]
    n_plan = metrics["planned_positions"]
    st.markdown(
        _metric_card(
            "Open Positions",
            f"{n_open}" + (f" (+{n_plan} planned)" if n_plan else ""),
        ),
        unsafe_allow_html=True,
    )
with c7:
    st.markdown(
        _metric_card(
            "BP / Capital Secured",
            f"{_money(metrics['buying_power'])} / {_money(metrics['capital_secured'])}",
            hint="BP ≈ cash; capital = sum of open collateral (CSP/spread width)",
        ),
        unsafe_allow_html=True,
    )

st.caption(
    f"Day P&L note: {metrics['day_pnl_note']} · "
    "Activity tab timestamps are fill times (PT). "
    "**Premium collected** = credits taken when opening; "
    "**Realized** = P&L after close (credit − close debit)."
)

# Portfolio Greeks bar
st.markdown(
    f"""
<div class="greeks-bar">
  <div><span class="greek-label">Portfolio Greeks</span>
    <span class="est-tag">{greeks['label']}</span></div>
  <div class="greek-item"><span class="greek-label">Δ Delta</span><br>
    <b>{greeks['delta']:+.1f}</b></div>
  <div class="greek-item"><span class="greek-label">Θ Theta</span><br>
    <b>{greeks['theta']:+.2f}</b></div>
  <div class="greek-item"><span class="greek-label">Γ Gamma</span><br>
    <b>{greeks['gamma']:+.2f}</b></div>
  <div class="greek-item"><span class="greek-label">ν Vega</span><br>
    <b>{greeks['vega']:+.2f}</b></div>
  <div style="color:#8b9bb4;font-size:0.75rem;max-width:28rem">{greeks['note']}</div>
</div>
""",
    unsafe_allow_html=True,
)

# B. Strategies in play strip
_in_play = strategies_in_play(ex)
st.markdown("#### Strategies in play")
if not _in_play:
    st.caption("No open strategies yet.")
    if st.button("🌱 Seed demo book", key="seed_empty_strat"):
        seeded = seed_demo_book(ex, reset=True)
        _set_last_action("ok", f"Demo book seeded — {len(seeded)} opens")
        if seeded:
            st.session_state["focus_position_id"] = seeded[0]["id"]
        st.rerun()
else:
    filt = st.session_state.get("strategy_filter")
    cols = st.columns(min(len(_in_play), 6) or 1)
    for i, row in enumerate(_in_play):
        with cols[i % len(cols)]:
            active = filt == row["strategy"]
            st.markdown(
                f'<div class="strat-card{" active" if active else ""}">'
                f'<div class="strat-name">{row["strategy"]}</div>'
                f'<div class="strat-meta">{row["open_count"]} open · '
                f'cap {_money(row["capital"])}</div>'
                f'<div>Unreal <span class="{_pnl_class(row["unrealized"])}">'
                f'{_money(row["unrealized"], True)}</span> · '
                f'Real <span class="{_pnl_class(row["realized"])}">'
                f'{_money(row["realized"], True)}</span></div></div>',
                unsafe_allow_html=True,
            )
            label = f"Filter {row['strategy']}" if not active else f"Clear filter ({row['strategy']})"
            if st.button(label, key=f"strat_filt_{row['strategy']}", use_container_width=True):
                st.session_state["strategy_filter"] = None if active else row["strategy"]
                st.rerun()
    if filt:
        st.caption(f"Positions filtered to **{filt}** — clear via the active card button.")

# Risk rejection / cap banner
_cfg_risk = load_defaults()
_risk_lim = risk_limits_from_config(_cfg_risk)
_book = evaluate_book(ex.portfolio.get("positions", []), _risk_lim)
st.markdown(
    f"**Portfolio capital/risk cap:** ${_book['max_portfolio_risk_usd']:,.0f} · "
    f"open risk ${_book['aggregate_open_risk']:,.0f} · "
    f"headroom ${_book['headroom']:,.0f} · "
    f"status `{_book['status']}` · auto_trim=`{_book['auto_trim']}`"
)
st.caption(
    "Open risk ≈ sum of max loss / capital at risk on open trades. "
    "Headroom = hard cap − open risk. "
    "BP ≈ cash; capital secured = collateral tied up (not subtracted from cash in this paper model)."
)
_last = ex.portfolio.get("last_risk_event")
if _last and _last.get("type") == "risk_rejected":
    st.error(
        f"RISK REJECTED (final — do not retry): {_last.get('underlying')} "
        f"{_last.get('strategy')} — {_last.get('reason')}"
    )
_trim = ex.portfolio.get("auto_trim_last")
if _trim and _trim.get("type") == "risk_trim":
    st.warning(
        f"Auto-trim: closed {_trim.get('underlying')} {_trim.get('strategy')} "
        f"— {_trim.get('reason') or 'enforced $50k cap'}"
    )

# Scanner status strip
envelope, scan_status = load_scan_envelope()
as_of = scan_status.get("as_of") or "—"
src = scan_status.get("source") or "—"
ok_cls = "status-ok" if scan_status.get("ok") else "status-bad"
kind = scan_status.get("source_kind") or ("local" if scan_status.get("local_ok") else "?")
st.markdown(
    f"**Scanner UI:** [{scanner_ui_url()}]({scanner_ui_url()}) · "
    f"**BASE:** `{scanner_base_url()}` · "
    f"**Data:** <span class='{ok_cls}'>{'OK' if scan_status.get('ok') else 'ERR'}</span> · "
    f"source=<span class='status-ok'>{kind}</span> · asOf=`{as_of}`",
    unsafe_allow_html=True,
)
if scan_status.get("remote_note"):
    st.caption(scan_status["remote_note"])


# ── Tabs ─────────────────────────────────────────────────────────────────
tab_pos, tab_act, tab_cand, tab_risk, tab_perf = st.tabs(
    ["Positions", "Activity", "Candidates", "Risk", "Performance"]
)

# ── Positions ────────────────────────────────────────────────────────────
with tab_pos:
    sub_open, sub_closed = st.tabs(["Open", "Closed"])
    filt = st.session_state.get("strategy_filter")
    focus_id = st.session_state.get("focus_position_id")

    with sub_open:
        open_pos = [
            p
            for p in ex.list_open()
            if (filt is None or p.get("strategy") == filt)
        ]
        if not open_pos:
            st.info("No open positions. Use **Seed demo book** or open from Candidates.")
            if st.button("🌱 Seed demo book", key="seed_empty_pos"):
                seeded = seed_demo_book(ex, reset=True)
                _set_last_action("ok", f"Demo book seeded — {len(seeded)} opens")
                if seeded:
                    st.session_state["focus_position_id"] = seeded[0]["id"]
                st.rerun()
        else:
            # Compact summary dataframe (actions live on cards)
            rows = []
            for p in open_pos:
                pct = pct_of_max_profit(p.get("unrealized_pnl"), p.get("max_profit"))
                ov = celebrity_overlay(p.get("underlying"))
                rows.append(
                    {
                        "id": p["id"],
                        "Symbol": p.get("underlying"),
                        "⭐": "⭐" if ov["is_priority"] else ("◇" if ov["is_honorable"] else ""),
                        "Strategy": p.get("strategy"),
                        "Qty": _contract_qty(p.get("legs") or []),
                        "Legs": _legs_summary(p.get("legs") or []),
                        "DTE": p.get("dte"),
                        "Credit": p.get("credit"),
                        "Mark": p.get("mark"),
                        "Unrealized": p.get("unrealized_pnl"),
                        "% Max": pct,
                        "Capital": p.get("capital"),
                        "Status": p.get("status"),
                    }
                )
            df = pd.DataFrame(rows)
            display = df.drop(columns=["id"])
            st.dataframe(
                display.style.format(
                    {
                        "Credit": "${:,.2f}",
                        "Mark": "${:,.2f}",
                        "Unrealized": "${:+,.2f}",
                        "Capital": "${:,.2f}",
                        "% Max": "{:.1f}%",
                    },
                    na_rep="—",
                ),
                use_container_width=True,
                hide_index=True,
            )
            st.caption(
                "Summary is sortable. **Close / mark actions are on each card below.** "
                "Money figures are **total ticket $** (not per-share)."
            )

            for p in open_pos:
                pid = p["id"]
                ov = celebrity_overlay(p.get("underlying"))
                ur = p.get("unrealized_pnl")
                pct = pct_of_max_profit(ur, p.get("max_profit"))
                pct_s = f"{pct:.1f}% max" if pct is not None else "— % max"
                badge = (
                    f'<span class="badge-priority">{ov["badge"]}</span>'
                    if ov.get("badge")
                    else ""
                )
                expanded = focus_id == pid
                header = (
                    f"{p.get('underlying')} · {p.get('strategy')} · "
                    f"{(p.get('status') or 'OPEN').upper()} · "
                    f"{_money(ur, True)} · {pct_s}"
                )
                with st.expander(header, expanded=expanded):
                    st.markdown(
                        f'<div class="pos-header">{p.get("underlying")} · '
                        f'{p.get("strategy")} · {(p.get("status") or "").upper()}'
                        f"{badge}</div>",
                        unsafe_allow_html=True,
                    )
                    if ov.get("caution"):
                        st.markdown(
                            f'<div class="caution-cap">{ov["caution"]}</div>',
                            unsafe_allow_html=True,
                        )

                    bes = _breakevens_for(p)
                    be_s = ", ".join(f"{b:.2f}" for b in bes) if bes else "—"
                    qty = _contract_qty(p.get("legs") or [])
                    m1, m2, m3, m4, m5, m6 = st.columns(6)
                    m1.metric("Qty", f"{qty}")
                    m2.metric("DTE / Expiry", f"{p.get('dte') or '—'} / {p.get('expiry') or '—'}")
                    m3.metric("Credit (ticket $)", _money(p.get("credit")))
                    m4.metric("Mark (ticket $)", _money(p.get("mark")))
                    m5.metric("Unrealized", _money(ur, True))
                    m6.metric("% of max profit", pct_s)
                    n1, n2, n3, n4 = st.columns(4)
                    n1.metric("Max profit", _money(p.get("max_profit")))
                    n2.metric("Max loss", _money(p.get("max_loss")))
                    n3.metric("Capital", _money(p.get("capital")))
                    n4.metric("Breakeven(s)", be_s)
                    st.caption(
                        f"Legs: `{_legs_summary(p.get('legs') or [])}` · "
                        f"Opened {_format_ts_pt(p.get('opened_at'))} · id `{pid[:8]}`"
                    )

                    st.markdown("**Close** — debit is **total $ for the ticket**, not per share.")
                    # Live mark slider first so we can show mapped debit + EST unrealized
                    credit = float(p.get("credit") or 0)
                    cur_frac = 0.5
                    if credit > 0 and p.get("mark") is not None:
                        cur_frac = min(1.0, max(0.0, float(p["mark"]) / credit))
                    frac = st.slider(
                        "Mark as fraction of credit (EST)",
                        0.0,
                        1.0,
                        float(round(cur_frac, 2)),
                        0.05,
                        key=f"mark_frac_{pid}",
                    )
                    mapped_debit = round(credit * frac, 2) if credit else 0.0
                    est_unreal = round(credit - mapped_debit, 2) if credit else 0.0
                    st.caption(
                        f"Mapped exit debit **{_money(mapped_debit)}** · "
                        f"EST unrealized if marked here: "
                        f"**{_money(est_unreal, True)}** "
                        f"({pct_of_max_profit(est_unreal, p.get('max_profit')) or '—'}% max)"
                    )
                    b_upd, b_close_mark, b_close_50, b_custom = st.columns(4)
                    with b_upd:
                        if st.button("Update mark", key=f"upd_{pid}"):
                            ex.update_mark(pid, mark_fraction=frac)
                            _set_last_action(
                                "ok",
                                f"Updated mark {p.get('underlying')} → {_money(mapped_debit)}",
                                pnl=est_unreal,
                                position_id=pid,
                            )
                            st.session_state["focus_position_id"] = pid
                            st.rerun()
                    with b_close_mark:
                        mark_px = p.get("mark")
                        est_m = _est_realized_on_close(p, float(mark_px) if mark_px is not None else None)
                        if st.button(
                            f"Close @ mark ({_money(mark_px)})",
                            key=f"cl_mark_{pid}",
                            type="primary",
                        ):
                            closed = ex.close_position(pid, price=None)
                            _set_last_action(
                                "ok" if (closed.get("realized_pnl") or 0) >= 0 else "bad",
                                f"Closed {closed.get('underlying')} @ mark",
                                pnl=closed.get("realized_pnl"),
                                position_id=pid,
                            )
                            st.session_state["focus_position_id"] = None
                            st.rerun()
                        st.caption(f"EST realized {_money(est_m, True)}")
                    with b_close_50:
                        half = round(credit * 0.5, 2) if credit else 0.0
                        est_50 = _est_realized_on_close(p, half)
                        if st.button(
                            f"Close @ 50% credit ({_money(half)})",
                            key=f"cl_50_{pid}",
                        ):
                            closed = ex.close_position(pid, price=half)
                            _set_last_action(
                                "ok" if (closed.get("realized_pnl") or 0) >= 0 else "bad",
                                f"Closed {closed.get('underlying')} @ 50% credit",
                                pnl=closed.get("realized_pnl"),
                                position_id=pid,
                            )
                            st.session_state["focus_position_id"] = None
                            st.rerun()
                        st.caption(f"EST realized {_money(est_50, True)}")
                    with b_custom:
                        # Empty default: use None sentinel via checkbox / number with None
                        use_custom = st.checkbox(
                            "Custom close debit",
                            key=f"use_custom_{pid}",
                            help="Total ticket $ to buy back (not per-share)",
                        )
                        custom_px = st.number_input(
                            "Close debit (total $)",
                            min_value=0.0,
                            value=float(p.get("mark") or (credit * 0.5 if credit else 0.0)),
                            step=5.0,
                            key=f"custom_px_{pid}",
                            disabled=not use_custom,
                            help="Total $ for the multi-leg ticket",
                        )
                        est_c = _est_realized_on_close(p, float(custom_px) if use_custom else None)
                        st.caption(f"EST realized {_money(est_c, True)}")
                        if st.button(
                            "Confirm close @ custom",
                            key=f"cl_custom_{pid}",
                            disabled=not use_custom,
                        ):
                            closed = ex.close_position(pid, price=float(custom_px))
                            _set_last_action(
                                "ok" if (closed.get("realized_pnl") or 0) >= 0 else "bad",
                                f"Closed {closed.get('underlying')} @ custom {_money(custom_px)}",
                                pnl=closed.get("realized_pnl"),
                                position_id=pid,
                            )
                            st.session_state["focus_position_id"] = None
                            st.rerun()

                    if st.button("Roll (stub)", key=f"roll_{pid}"):
                        st.info("Roll is a stub — close + re-open from Candidates for now.")

            # clear focus after render so next rerun doesn't keep forcing expand
            if focus_id and any(p["id"] == focus_id for p in open_pos):
                pass  # keep until user navigates away / closes

    with sub_closed:
        closed = sorted(
            ex.list_closed(),
            key=lambda p: p.get("closed_at") or "",
            reverse=True,
        )
        if filt:
            closed = [p for p in closed if p.get("strategy") == filt]
        if not closed:
            st.info("No closed positions yet.")
        else:
            crows = []
            for p in closed:
                crows.append(
                    {
                        "Symbol": p.get("underlying"),
                        "Strategy": p.get("strategy"),
                        "Realized": p.get("realized_pnl"),
                        "Days held": days_held(p.get("opened_at"), p.get("closed_at")),
                        "Closed at": _format_ts_pt(p.get("closed_at")),
                        "Credit": p.get("credit"),
                        "Close debit": p.get("close_price"),
                    }
                )
            cdf = pd.DataFrame(crows)
            st.dataframe(
                cdf.style.format(
                    {
                        "Realized": "${:+,.2f}",
                        "Credit": "${:,.2f}",
                        "Close debit": "${:,.2f}",
                        "Days held": "{:.2f}",
                    },
                    na_rep="—",
                ),
                use_container_width=True,
                hide_index=True,
            )

# ── Activity ─────────────────────────────────────────────────────────────
with tab_act:
    fills = ex.list_fills()
    st.caption(
        "Fill timestamps shown in Pacific (PT). "
        "Day P&L above uses UTC calendar day for 'closed today' + open unrealized (EST)."
    )
    if not fills:
        st.info("No fills yet.")
    else:
        frows = []
        for f in fills:
            ftype = f.get("type") or ("open" if f.get("fill_price") is not None else "?")
            reason = f.get("reason") or f.get("notes") or ""
            if ftype == "risk_trim":
                reason = reason or f"freed ${float(f.get('risk_freed') or 0):,.0f}"
            frows.append(
                {
                    "Time (PT)": _format_ts_pt(f.get("ts")),
                    "Type": ftype,
                    "Symbol": f.get("underlying"),
                    "Strategy": f.get("strategy"),
                    "Fill $": f.get("fill_price"),
                    "Realized": f.get("realized_pnl"),
                    "Risk/Reason": reason[:120] if reason else "",
                    "Position": (f.get("position_id") or "")[:8],
                }
            )
        st.dataframe(pd.DataFrame(frows), use_container_width=True, hide_index=True)

# ── Candidates ───────────────────────────────────────────────────────────
with tab_cand:
    st.markdown("**Open path:** use **Open this trade** on a row to paper-fill one candidate.")
    st.caption(
        "Sidebar **Bulk scan → paper open** walks every candidate. "
        "This button opens only the row you click."
    )
    if envelope is None:
        st.error(scan_status.get("error") or "Could not load scan JSON")
    else:
        ctx = load_portfolio_ctx(st.session_state.capital_ctx_path)
        cands = build_candidates(envelope, portfolio=ctx, cfg=load_defaults())
        st.markdown(
            f"**{len(cands)}** symbols from scan · asOf `{as_of}` · source `{src}`"
        )
        for row in cands:
            ov = celebrity_overlay(row.get("symbol"))
            badge_html = (
                f'<span class="badge-priority">{ov["badge"]}</span>'
                if ov.get("badge")
                else ""
            )
            cols = st.columns([1.4, 0.8, 1.2, 1.5, 1, 1, 1.4])
            cols[0].markdown(
                f"**{row['symbol']}**{badge_html}",
                unsafe_allow_html=True,
            )
            if ov.get("caution"):
                cols[0].markdown(
                    f'<div class="caution-cap">{ov["caution"]}</div>',
                    unsafe_allow_html=True,
                )
            cols[1].write(_money(row["price"]))
            cols[2].write(row.get("bias") or "—")
            if row["skipped"]:
                cols[3].caption("skipped")
                continue
            tmpl = "🧾 template" if row.get("is_template") else "💰 quoted"
            cols[3].write(f"{row['strategy']} ({tmpl})")
            cols[4].write(_money(row.get("net_premium")))
            cols[5].write(f"DTE {row.get('target_dte') or '—'}")
            # Prefer volume / IV cols when celebrity overlay asks and scan has them
            if ov.get("prefer_volume_cols"):
                vol_bits = []
                for k in ("options_volume", "option_volume", "rel_volume", "relative_volume", "iv_rank"):
                    if row.get(k) is not None:
                        vol_bits.append(f"{k}={row[k]}")
                if vol_bits:
                    cols[5].caption(" · ".join(vol_bits[:3]))
            plan = row.get("plan")
            if plan is not None and cols[6].button(
                "Open this trade",
                key=f"open_{row['symbol']}_{row['strategy']}",
                help="Paper-fill this single candidate (not bulk)",
            ):
                ticket = ex.execute(plan)
                if ticket.status == "risk_rejected":
                    reason = (
                        ticket.plan.notes
                        or ex.portfolio.get("last_risk_event", {}).get("reason")
                        or "risk_rejected"
                    )
                    _set_last_action(
                        "bad",
                        f"RISK REJECTED (final): {row['symbol']} — {reason}",
                    )
                elif ticket.status == "template_only":
                    # find planned position id
                    planned_id = None
                    for p in reversed(ex.list_open()):
                        if (
                            p.get("underlying") == row["symbol"]
                            and p.get("strategy") == row["strategy"]
                            and p.get("status") == "planned"
                        ):
                            planned_id = p["id"]
                            break
                    _set_last_action(
                        "amber",
                        f"{row['symbol']}: template/planned only — no live premium, not filled",
                        position_id=planned_id,
                    )
                    st.session_state["focus_position_id"] = planned_id
                else:
                    new_id = None
                    for p in reversed(ex.list_open()):
                        if (
                            p.get("underlying") == row["symbol"]
                            and p.get("strategy") == row["strategy"]
                            and p.get("status") == "open"
                        ):
                            new_id = p["id"]
                            break
                    _set_last_action(
                        "ok",
                        f"Opened {row['symbol']} {row['strategy']} — fill {_money(ticket.fill_price)}",
                        pnl=None,
                        position_id=new_id,
                    )
                    st.session_state["focus_position_id"] = new_id
                st.rerun()
            with st.expander(f"Details — {row['symbol']}"):
                st.write(row.get("reason"))
                st.write(row.get("notes"))
                detail = {
                    k: row[k]
                    for k in (
                        "max_profit",
                        "max_loss",
                        "capital",
                        "iv_rank",
                        "days_to_earnings",
                        "is_template",
                        "options_volume",
                        "option_volume",
                        "rel_volume",
                        "relative_volume",
                    )
                    if k in row and row[k] is not None
                }
                st.json(detail)

# ── Risk ─────────────────────────────────────────────────────────────────
with tab_risk:
    cfg = load_defaults()
    risk_limits = risk_limits_from_config(cfg)
    book = evaluate_book(ex.portfolio.get("positions", []), risk_limits)
    status_cls = {
        "ok": "status-ok",
        "soft_warn": "status-warn",
        "hard_breach": "status-bad",
    }.get(book["status"], "")
    st.markdown("#### Portfolio hard risk limit ($50k)")
    r1, r2, r3, r4, r5 = st.columns(5)
    r1.metric("Aggregate open risk", _money(book["aggregate_open_risk"]))
    r2.metric("Hard cap", _money(book["max_portfolio_risk_usd"]))
    r3.metric("Headroom", _money(book["headroom"]))
    r4.metric("Utilization", f"{book['utilization_pct']:.1f}%")
    r5.markdown(
        f'<div class="metric-card"><div class="metric-label">Status</div>'
        f'<div class="metric-value {status_cls}">{book["status"]}</div></div>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"Soft warn at {_money(book['soft_warn_usd'])} "
        f"({book['soft_warn_pct']*100:.0f}%) — status only, no auto-trim at soft. "
        f"Hard breach trims highest-risk opens first. "
        f"Open risk ≈ max loss / capital at risk; headroom = cap − open risk."
    )
    if st.button("Enforce $50k trim", type="primary", key="enforce_50k_trim"):
        result = enforce_hard_limits(ex, risk_limits)
        if result["trimmed"]:
            _set_last_action("amber", result["message"])
        else:
            _set_last_action("ok", result["message"])
        st.rerun()

    st.divider()
    st.markdown("#### Payoff @ expiration")
    open_for_risk = [p for p in ex.list_open() if p.get("status") == "open"]
    if not open_for_risk:
        st.info("Select/seed an open position to view payoff-at-expiration.")
    else:
        labels = {
            f"{p['underlying']} · {p['strategy']} · {p['id'][:8]}": p for p in open_for_risk
        }
        choice = st.selectbox("Position for risk chart", list(labels.keys()), key="risk_pick")
        pos = labels[choice]
        series = payoff_series(pos)
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=series["spots"],
                y=series["pnl"],
                mode="lines",
                name="P/L @ expiry",
                line=dict(color="#58a6ff", width=2),
                fill="tozeroy",
                fillcolor="rgba(88,166,255,0.12)",
            )
        )
        if series.get("max_profit") is not None:
            fig.add_hline(
                y=float(series["max_profit"]),
                line_dash="dot",
                line_color="#3dd68c",
                annotation_text="Max profit",
            )
        if series.get("max_loss") is not None:
            fig.add_hline(
                y=-abs(float(series["max_loss"])),
                line_dash="dot",
                line_color="#f85149",
                annotation_text="Max loss",
            )
        fig.add_hline(y=0, line_color="#8b9bb4", line_width=1)
        for be in series.get("breakevens") or []:
            fig.add_vline(
                x=be, line_dash="dash", line_color="#c9a227", annotation_text=f"BE {be:.1f}"
            )
        for k in series.get("strikes") or []:
            fig.add_vline(x=k, line_color="#243041", line_width=1)
        if series.get("center"):
            fig.add_vline(
                x=series["center"],
                line_color="#3dd68c",
                line_width=1,
                annotation_text="Spot EST",
            )
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0b0f14",
            plot_bgcolor="#111821",
            title=f"Payoff @ expiration — {pos['underlying']} {pos['strategy']}",
            xaxis_title="Underlying price",
            yaxis_title="P/L ($)",
            height=420,
            margin=dict(l=40, r=20, t=50, b=40),
        )
        st.plotly_chart(fig, use_container_width=True)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Max profit", _money(series.get("max_profit")))
        m2.metric("Max loss", _money(series.get("max_loss")))
        m3.metric("Breakevens", ", ".join(f"{b:.2f}" for b in (series.get("breakevens") or [])) or "—")
        m4.metric("Credit", _money(pos.get("credit")))

# ── Performance ──────────────────────────────────────────────────────────
with tab_perf:
    st.markdown("#### Cumulative realized P&L")
    fills = ex.list_fills()
    closes = [f for f in reversed(fills) if f.get("type") == "close"]
    unreal = sum(float(p.get("unrealized_pnl") or 0) for p in ex.list_open() if p.get("status") == "open")
    if not closes:
        st.caption(f"No closes yet. Open unrealized (EST): {_money(unreal, True)}")
    else:
        cum = 0.0
        xs, ys = [], []
        for f in closes:
            cum += float(f.get("realized_pnl") or 0)
            xs.append(_format_ts_pt(f.get("ts")))
            ys.append(cum)
        fig2 = go.Figure()
        fig2.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines+markers",
                name="Cumulative realized",
                line=dict(color="#3dd68c"),
                hovertemplate="%{x}<br>Cum realized: $%{y:+,.2f}<extra></extra>",
            )
        )
        # Annotate open unrealized on last point
        fig2.add_annotation(
            x=xs[-1],
            y=ys[-1],
            text=f"Open unrealized {_money(unreal, True)}",
            showarrow=True,
            arrowhead=2,
            ax=40,
            ay=-40,
            font=dict(color="#58a6ff", size=11),
        )
        # Dual reference: realized + unrealized total
        fig2.add_hline(
            y=ys[-1] + unreal,
            line_dash="dot",
            line_color="#58a6ff",
            annotation_text=f"Realized+unrealized {_money(ys[-1] + unreal, True)}",
        )
        fig2.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0b0f14",
            plot_bgcolor="#111821",
            height=340,
            margin=dict(l=40, r=20, t=30, b=40),
            yaxis_title="Cumulative realized ($)",
            xaxis_title="Close time (PT)",
            legend=dict(orientation="h"),
        )
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("#### Strategy performance")
    st.caption(
        "Premium collected = credits when opened. Realized = closed P&L. "
        "Win rate ignores flat ($0) closes."
    )
    srows = strategy_performance(ex)
    if not srows:
        st.info("No strategy data yet.")
        if st.button("🌱 Seed demo book", key="seed_empty_perf"):
            seeded = seed_demo_book(ex, reset=True)
            _set_last_action("ok", f"Demo book seeded — {len(seeded)} opens")
            st.rerun()
    else:
        sdf = pd.DataFrame(
            [
                {
                    "Strategy": r["strategy"],
                    "Open #": r["open_count"],
                    "Unrealized": r["unrealized"],
                    "Closed #": r["closed_count"],
                    "Realized": r["realized"],
                    "Win rate %": r["win_rate"],
                    "Avg win": r["avg_win"],
                    "Avg loss": r["avg_loss"],
                    "Premium collected": r["premium_collected"],
                }
                for r in srows
            ]
        )
        st.dataframe(
            sdf.style.format(
                {
                    "Unrealized": "${:+,.2f}",
                    "Realized": "${:+,.2f}",
                    "Avg win": "${:+,.2f}",
                    "Avg loss": "${:+,.2f}",
                    "Premium collected": "${:,.2f}",
                    "Win rate %": "{:.1f}",
                },
                na_rep="—",
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("#### Ticker performance")
    st.caption("GOOG/GOOGL dual-class rolls up under GOOGL (no double-count).")
    trows = ticker_performance(ex)
    if trows:
        tdf = pd.DataFrame(
            [
                {
                    "Ticker": r["ticker"],
                    "Open #": r["open_count"],
                    "Unrealized": r["unrealized"],
                    "Closed #": r["closed_count"],
                    "Realized": r["realized"],
                    "Win rate %": r["win_rate"],
                    "Avg win": r["avg_win"],
                    "Avg loss": r["avg_loss"],
                    "Premium collected": r["premium_collected"],
                }
                for r in trows
            ]
        )
        st.dataframe(
            tdf.style.format(
                {
                    "Unrealized": "${:+,.2f}",
                    "Realized": "${:+,.2f}",
                    "Avg win": "${:+,.2f}",
                    "Avg loss": "${:+,.2f}",
                    "Premium collected": "${:,.2f}",
                    "Win rate %": "{:.1f}",
                },
                na_rep="—",
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("#### Premium charts")
    all_pos = ex.portfolio.get("positions", [])
    by_strat: dict[str, float] = {}
    by_ticker: dict[str, float] = {}
    for p in all_pos:
        prem = float(p.get("credit") or 0)
        if p.get("credit_debit") != "credit":
            continue
        if p.get("status") not in ("open", "closed"):
            continue
        by_strat[p.get("strategy") or "?"] = by_strat.get(p.get("strategy") or "?", 0) + prem
        tk = rollup_ticker(p.get("underlying"))
        by_ticker[tk] = by_ticker.get(tk, 0) + prem

    i1, i2 = st.columns(2)
    with i1:
        st.markdown("##### Premium by strategy")
        if by_strat:
            sdf2 = pd.DataFrame(
                [{"Strategy": k, "Premium": v} for k, v in sorted(by_strat.items())]
            )
            st.bar_chart(sdf2.set_index("Strategy"), color="#3dd68c")
            st.dataframe(sdf2, use_container_width=True, hide_index=True)
        else:
            st.caption("No premium yet.")
    with i2:
        st.markdown("##### Premium by ticker")
        if by_ticker:
            tdf2 = pd.DataFrame(
                [{"Ticker": k, "Premium": v} for k, v in sorted(by_ticker.items())]
            )
            st.bar_chart(tdf2.set_index("Ticker"), color="#58a6ff")
            st.dataframe(tdf2, use_container_width=True, hide_index=True)
        else:
            st.caption("No premium yet.")
