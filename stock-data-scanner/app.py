"""Stock Data Scanner — Streamlit dashboard + scan-latest.json export."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from celebrity_priority import (
    PRIORITY_ROWS,
    SCAN_DATE,
    SOURCE_REPORT,
    SOURCE_REPORT_NOTE,
    honorable_only,
    priority_only,
)
from scan import (
    DEFAULT_UNIVERSE,
    SCAN_PATH,
    fetch_history,
    get_quote_row,
    write_scan,
)

st.set_page_config(
    page_title="Stock Data Scanner",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Dark finance theme
st.markdown(
    """
<style>
    .stApp { background-color: #0b0f14; color: #e6edf3; }
    [data-testid="stSidebar"] { background-color: #111821; }
    h1, h2, h3 { color: #e6edf3 !important; }
    .up { color: #3dd68c; font-weight: 600; }
    .down { color: #f85149; font-weight: 600; }
    .metric-card {
        background: #151c25; border: 1px solid #243041; border-radius: 10px;
        padding: 0.85rem 1rem; margin-bottom: 0.5rem;
    }
    .metric-label { color: #9aa8bc; font-size: 0.75rem; text-transform: uppercase; }
    .metric-value { font-size: 1.15rem; font-weight: 600; margin-top: 0.15rem; }
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

</style>
""",
    unsafe_allow_html=True,
)


def fmt(v: Any, kind: str = "num") -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    try:
        if kind == "price":
            return f"${float(v):,.2f}"
        if kind == "pct":
            return f"{float(v):+.2f}%"
        if kind == "chg":
            return f"{float(v):+,.2f}"
        if kind == "vol":
            x = float(v)
            if abs(x) >= 1e9:
                return f"{x/1e9:.2f}B"
            if abs(x) >= 1e6:
                return f"{x/1e6:.2f}M"
            if abs(x) >= 1e3:
                return f"{x/1e3:.1f}K"
            return f"{x:,.0f}"
        if kind == "cap":
            x = float(v)
            if abs(x) >= 1e12:
                return f"${x/1e12:.2f}T"
            if abs(x) >= 1e9:
                return f"${x/1e9:.2f}B"
            if abs(x) >= 1e6:
                return f"${x/1e6:.2f}M"
            return f"${x:,.0f}"
        if kind == "yield":
            # Yahoo often returns fraction; if > 1 treat as already %
            x = float(v)
            if 0 < abs(x) < 1:
                x *= 100
            return f"{x:.2f}%"
        return f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return "—"


def color_class(v: Any) -> str:
    try:
        if v is None:
            return ""
        return "up" if float(v) >= 0 else "down"
    except (TypeError, ValueError):
        return ""


def load_scan_file() -> dict | None:
    """Instant load of last written envelope — never blocks on Yahoo."""
    try:
        if SCAN_PATH.is_file():
            return json.loads(SCAN_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return None


# --- Background Yahoo refresh (keeps UI responsive on "Refresh now") ---
_REFRESH_LOCK = threading.Lock()
_REFRESH_STATE: dict[str, Any] = {
    "running": False,
    "error": None,
    "started_at": 0.0,
    "finished_at": 0.0,
}


def _scan_mtime() -> float:
    try:
        return SCAN_PATH.stat().st_mtime if SCAN_PATH.is_file() else 0.0
    except OSError:
        return 0.0


def _bg_write_scan(universe: list[str]) -> None:
    err: str | None = None
    try:
        write_scan(universe)
    except Exception as exc:  # noqa: BLE001 — surface to UI banner
        err = str(exc)
    finally:
        with _REFRESH_LOCK:
            _REFRESH_STATE["error"] = err
            _REFRESH_STATE["running"] = False
            _REFRESH_STATE["finished_at"] = time.time()


def start_background_refresh(universe: list[str]) -> bool:
    """Kick Yahoo write_scan off the Streamlit request path. True if started."""
    with _REFRESH_LOCK:
        if _REFRESH_STATE["running"]:
            return False
        _REFRESH_STATE["running"] = True
        _REFRESH_STATE["error"] = None
        _REFRESH_STATE["started_at"] = time.time()
        _REFRESH_STATE["finished_at"] = 0.0
    thread = threading.Thread(
        target=_bg_write_scan,
        args=(list(universe),),
        name="scan-yahoo-refresh",
        daemon=True,
    )
    thread.start()
    return True


def refresh_running() -> bool:
    with _REFRESH_LOCK:
        return bool(_REFRESH_STATE["running"])


def refresh_error() -> str | None:
    with _REFRESH_LOCK:
        return _REFRESH_STATE.get("error")


@st.cache_data(ttl=55, show_spinner=False)
def cached_scan(universe_key: str) -> dict:
    universe = [s.strip().upper() for s in universe_key.split(",") if s.strip()]
    return write_scan(universe)


@st.cache_data(ttl=120, show_spinner=False)
def cached_history(symbol: str, period: str):
    """Cache chart history so refresh poll reruns do not re-hit Yahoo."""
    return fetch_history(symbol, period)


def style_overview(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    def _chg_color(val):
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return "color: #8b9bb4"
        try:
            return "color: #3dd68c; font-weight: 600" if float(val) >= 0 else "color: #f85149; font-weight: 600"
        except (TypeError, ValueError):
            return ""

    styler = df.style.map(_chg_color, subset=["Change $", "Change %"])
    styler = styler.format(
        {
            "Price": lambda v: fmt(v, "price"),
            "Change $": lambda v: fmt(v, "chg"),
            "Change %": lambda v: fmt(v, "pct"),
            "Volume": lambda v: fmt(v, "vol"),
            "Market Cap": lambda v: fmt(v, "cap"),
            "Day High": lambda v: fmt(v, "price"),
            "Day Low": lambda v: fmt(v, "price"),
            "Prev Close": lambda v: fmt(v, "price"),
            "Name": lambda v: v if v else "—",
        },
        na_rep="—",
    )
    return styler


def _price_lookup(results: list[dict]) -> dict[str, dict]:
    return {r.get("symbol"): r for r in results if r.get("symbol")}


def render_market_tab(results: list[dict], chart_period: str) -> None:
    """Existing overview / detail / chart behavior."""
    st.subheader("Overview")
    rows = [get_quote_row(r) for r in results]
    overview = pd.DataFrame(rows)

    if results:
        cols = st.columns(min(4, len(results)))
        for i, col in enumerate(cols):
            r = results[i]
            chg = r.get("changePct")
            cls = color_class(chg)
            with col:
                st.markdown(
                    f"""<div class="metric-card">
                    <div class="metric-label">{r.get("symbol")}</div>
                    <div class="metric-value">{fmt(r.get("price"), "price")}</div>
                    <div class="{cls}">{fmt(chg, "pct")} · {fmt(r.get("change"), "chg")}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )

    if not overview.empty:
        st.dataframe(style_overview(overview), use_container_width=True, hide_index=True)
    else:
        st.warning("No quote data returned.")

    st.subheader("Ticker detail")
    symbols = [r.get("symbol") for r in results if r.get("symbol")]
    if not symbols:
        st.info("No tickers to display.")
        return

    selected = st.selectbox("Select ticker", symbols, index=0, key="market_ticker")
    detail = next((r for r in results if r.get("symbol") == selected), None)

    if detail:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(
                f"""<div class="metric-card"><div class="metric-label">Last</div>
                <div class="metric-value">{fmt(detail.get("price"), "price")}</div></div>""",
                unsafe_allow_html=True,
            )
        with c2:
            cls = color_class(detail.get("changePct"))
            st.markdown(
                f"""<div class="metric-card"><div class="metric-label">Change</div>
                <div class="metric-value {cls}">{fmt(detail.get("change"), "chg")} ({fmt(detail.get("changePct"), "pct")})</div></div>""",
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                f"""<div class="metric-card"><div class="metric-label">Volume</div>
                <div class="metric-value">{fmt(detail.get("volume"), "vol")}</div></div>""",
                unsafe_allow_html=True,
            )
        with c4:
            st.markdown(
                f"""<div class="metric-card"><div class="metric-label">Market Cap</div>
                <div class="metric-value">{fmt(detail.get("marketCap"), "cap")}</div></div>""",
                unsafe_allow_html=True,
            )

        left, right = st.columns(2)
        with left:
            st.markdown("**Fundamentals & range**")
            fund_rows = [
                ("Name", detail.get("name") or "—"),
                ("Sector", detail.get("sector") or "—"),
                ("Industry", detail.get("industry") or "—"),
                ("Open", fmt(detail.get("open"), "price")),
                ("Day High", fmt(detail.get("dayHigh"), "price")),
                ("Day Low", fmt(detail.get("dayLow"), "price")),
                ("Prev Close", fmt(detail.get("previousClose"), "price")),
                ("Bid", fmt(detail.get("bid"), "price")),
                ("Ask", fmt(detail.get("ask"), "price")),
                ("P/E", fmt(detail.get("pe"))),
                ("EPS", fmt(detail.get("eps"))),
                ("Beta", fmt(detail.get("beta"))),
                ("Div Yield", fmt(detail.get("dividendYield"), "yield")),
                ("52w High", fmt(detail.get("fiftyTwoWeekHigh"), "price")),
                ("52w Low", fmt(detail.get("fiftyTwoWeekLow"), "price")),
                ("Avg Volume", fmt(detail.get("avgVolume"), "vol")),
            ]
            st.table(pd.DataFrame(fund_rows, columns=["Field", "Value"]))

        with right:
            st.markdown("**Trend · Liquidity · Earnings**")
            tr = detail.get("trend") or {}
            liq = detail.get("liquidity") or {}
            earn = detail.get("earnings") or {}
            extra = [
                ("Trend bias", tr.get("bias") or "—"),
                ("SMA20", fmt(tr.get("sma20"), "price")),
                ("SMA50", fmt(tr.get("sma50"), "price")),
                ("SMA200", fmt(tr.get("sma200"), "price")),
                ("Price vs SMA50 %", fmt(tr.get("priceVsSma50Pct"), "pct")),
                ("Volume ratio", fmt(liq.get("volumeRatio"))),
                ("Next earnings", earn.get("nextDate") or "—"),
                ("Days to earnings", earn.get("daysToEarnings") if earn.get("daysToEarnings") is not None else "—"),
            ]
            st.table(pd.DataFrame(extra, columns=["Field", "Value"]))

            markers = detail.get("markers") or {}
            miss = markers.get("missing") or []
            if miss:
                st.caption("Missing markers: " + ", ".join(miss))

        st.markdown(f"**Price chart — {selected} ({chart_period})**")
        hist = cached_history(selected, chart_period)
        if hist is not None and not hist.empty and "Close" in hist.columns:
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=hist.index,
                    y=hist["Close"],
                    mode="lines",
                    name="Close",
                    line=dict(color="#58a6ff", width=2),
                    fill="tozeroy",
                    fillcolor="rgba(88,166,255,0.08)",
                )
            )
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="#0b0f14",
                plot_bgcolor="#0b0f14",
                margin=dict(l=40, r=20, t=30, b=40),
                height=380,
                xaxis_title=None,
                yaxis_title="Price",
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No history available for this period.")


def render_celebrity_tab(results: list[dict]) -> None:
    """Celebrity Priority: ranked moves from the scan report (no invented data)."""
    st.subheader("Celebrity Priority")
    st.caption(
        f"Scan date: **{SCAN_DATE} PT** · "
        "Many 13Fs as of **2026-06-30** (~2.5 mo lag); Pelosi / STOCK Act disclosures can lag ~45 days. "
        "Amounts for political households are disclosure brackets, not exact fills."
    )
    st.caption(SOURCE_REPORT_NOTE)
    report_path = str(SOURCE_REPORT) if SOURCE_REPORT.exists() else "/workspace/celebrity-portfolio-scan-2026-09-18.md"
    st.markdown(
        f"Full report: `{report_path}` "
        f"(also `/workspace/celebrity-portfolio-scan-2026-09-18.md`)."
    )

    by_sym = _price_lookup(results)
    n_pri = len(priority_only())
    n_hon = len(honorable_only())
    st.markdown(f"**{n_pri} ranked** + **{n_hon} honorable mentions** encoded from the report.")

    table_rows = []
    missing_live: list[str] = []
    for r in PRIORITY_ROWS:
        sym = r["symbol"]
        quote = by_sym.get(sym)
        live_price = quote.get("price") if quote else None
        live_chg = quote.get("changePct") if quote else None
        if quote is None:
            missing_live.append(sym)
        table_rows.append(
            {
                "Rank": r["rank"] if r["rank"] is not None else "HM",
                "Ticker": sym,
                "Company": r["company"],
                "Investor / celebrity": r["investor"],
                "Triggering move": r["what_changed"],
                "Period": r["period"],
                "Why it made the list": r["why"],
                "Live price": live_price,
                "Live chg %": live_chg,
                "Honorable": r["honorable"],
            }
        )

    df = pd.DataFrame(table_rows)
    display = df.drop(columns=["Honorable"])
    st.dataframe(
        display.style.format(
            {
                "Live price": lambda v: fmt(v, "price"),
                "Live chg %": lambda v: fmt(v, "pct"),
            },
            na_rep="—",
        ),
        use_container_width=True,
        hide_index=True,
        height=420,
    )

    if missing_live:
        st.warning("No live quote in current scan envelope for: " + ", ".join(missing_live))
    else:
        st.caption("Live prices shown when the ticker is in the current scan envelope.")

    st.markdown("#### Full “why” detail")
    labels = []
    for r in PRIORITY_ROWS:
        prefix = f"#{r['rank']}" if r["rank"] is not None else "HM"
        labels.append(f"{prefix} · {r['symbol']} — {r['company']}")
    choice = st.selectbox("Select row for full text", labels, key="celeb_detail")
    idx = labels.index(choice)
    row = PRIORITY_ROWS[idx]
    quote = by_sym.get(row["symbol"])

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            f"""<div class="metric-card"><div class="metric-label">Ticker</div>
            <div class="metric-value">{row["symbol"]}</div></div>""",
            unsafe_allow_html=True,
        )
    with c2:
        price_txt = fmt(quote.get("price"), "price") if quote else "—"
        st.markdown(
            f"""<div class="metric-card"><div class="metric-label">Live price</div>
            <div class="metric-value">{price_txt}</div></div>""",
            unsafe_allow_html=True,
        )
    with c3:
        chg = quote.get("changePct") if quote else None
        cls = color_class(chg)
        st.markdown(
            f"""<div class="metric-card"><div class="metric-label">Live chg %</div>
            <div class="metric-value {cls}">{fmt(chg, "pct")}</div></div>""",
            unsafe_allow_html=True,
        )

    st.markdown(f"**Investor / celebrity:** {row['investor']}")
    st.markdown(f"**Triggering move:** {row['what_changed']}")
    st.markdown(f"**Period:** {row['period']}")
    st.markdown(f"**Why it made the list:** {row['why']}")

    with st.expander("Show all rows as expandable cards", expanded=False):
        for r in PRIORITY_ROWS:
            prefix = f"#{r['rank']}" if r["rank"] is not None else "HM"
            q = by_sym.get(r["symbol"])
            price_bit = f" · live {fmt(q.get('price'), 'price')}" if q else " · no live quote"
            with st.expander(f"{prefix} {r['symbol']} — {r['company']}{price_bit}"):
                st.write(f"**Investor:** {r['investor']}")
                st.write(f"**Trigger:** {r['what_changed']}")
                st.write(f"**Period:** {r['period']}")
                st.write(f"**Why:** {r['why']}")


def main() -> None:
    st.title("📈 Stock Data Scanner")
    st.caption("Live quotes via Yahoo Finance · scan export → `scan-latest.json`")

    with st.sidebar:
        st.header("Watchlist")
        default_str = ", ".join(DEFAULT_UNIVERSE)
        tickers_raw = st.text_area(
            "Tickers (comma-separated)",
            value=default_str,
            height=100,
        )
        universe = [t.strip().upper() for t in tickers_raw.replace("\n", ",").split(",") if t.strip()]
        if not universe:
            universe = list(DEFAULT_UNIVERSE)

        st.divider()
        auto = st.checkbox("Auto-refresh (~60s)", value=False)
        if st.button("🔄 Refresh now", use_container_width=True):
            # Do NOT block this click on Yahoo — start background write_scan and
            # keep rendering the last good scan-latest.json so settle stays fast.
            cached_scan.clear()
            st.session_state["_refresh_baseline_mtime"] = _scan_mtime()
            st.session_state["_refresh_pending"] = True
            start_background_refresh(universe)
            st.rerun()

        st.divider()
        st.markdown(f"**Export:** `{SCAN_PATH.name}`")
        st.caption("schema: stock-data-scanner.scan/v0.1")

        periods = ["1d", "5d", "1mo", "3mo", "1y"]
        chart_period = st.radio("Chart period", periods, index=2, horizontal=True)

    universe_key = ",".join(universe)

    # Always paint from last good file first (sub-second). Yahoo never blocks the
    # click handler; a background thread updates scan-latest.json, then we reload.
    envelope = load_scan_file()
    if envelope is None:
        with st.spinner("First-time fetch from Yahoo…"):
            envelope = cached_scan(universe_key)

    pending = bool(st.session_state.get("_refresh_pending"))
    running = refresh_running()
    baseline = float(st.session_state.get("_refresh_baseline_mtime") or 0.0)
    mtime = _scan_mtime()
    just_finished = False

    if pending and not running:
        # Background finished — pick up new file (or surface error) and clear flag.
        st.session_state.pop("_refresh_pending", None)
        st.session_state.pop("_refresh_baseline_mtime", None)
        pending = False
        just_finished = True
        err = refresh_error()
        if err:
            st.warning(f"Refresh failed: {err}")
        else:
            fresh = load_scan_file()
            if fresh is not None:
                envelope = fresh
            if mtime > baseline:
                st.toast("Scan refreshed from Yahoo", icon="✅")
    elif pending and running:
        st.info("Refreshing live quotes from Yahoo in the background… showing last good scan.")

    results = envelope.get("results") or []
    # Prefer showing requested universe order when file has extras/missing
    by_sym = {r.get("symbol"): r for r in results if r.get("symbol")}
    ordered = [by_sym[s] for s in universe if s in by_sym]
    if ordered:
        results = ordered

    as_of = envelope.get("asOf", "—")
    if pending and running:
        status_bit = " · _refreshing…_"
    elif just_finished:
        status_bit = " · _refresh complete_"
    else:
        status_bit = " · _UI loads last scan; Refresh pulls Yahoo in background._"
    st.markdown(
        f"**As of (UTC):** `{as_of}` · **Source:** yahoo_finance · **Wrote:** `{SCAN_PATH}`"
        f"{status_bit}"
    )

    tab_market, tab_celeb = st.tabs(["Market", "Celebrity Priority"])
    with tab_market:
        render_market_tab(results, chart_period)
    with tab_celeb:
        render_celebrity_tab(results)

    # Poll AFTER painting last-good UI so the click path never blocks on Yahoo.
    if pending and running:
        time.sleep(0.5)
        st.rerun()

    if auto and not refresh_running() and not pending:
        time.sleep(60)
        cached_scan.clear()
        st.session_state["_refresh_baseline_mtime"] = _scan_mtime()
        st.session_state["_refresh_pending"] = True
        start_background_refresh(universe)
        st.rerun()


if __name__ == "__main__":
    main()
