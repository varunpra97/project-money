import LivePrice from "../components/LivePrice";
import { lazy, Suspense, useMemo, useState } from "react";
import { RANGES, useApi } from "../lib/api";
import { cls, fmtDate, money, moneySigned, pctPts } from "../lib/fmt";

const Chart = lazy(() => import("../components/Chart"));

interface Summary {
  account_value: number; buying_power: number; day_pnl: number; day_pnl_pct: number;
  total_pnl: number; open_positions: number; greeks: Record<string, number>; as_of: string;
}
interface PositionLeg {
  side?: string; option_type?: string; strike?: number; quantity?: number; expiry?: string | null;
}
interface Position {
  expiry?: string | null; legs?: PositionLeg[];
  day_pnl?: number | null; return_pct?: number | null; equity?: number | null;
  id: string; underlying: string; strategy: string; display_name: string;
  opened_at: string; dte: number; qty: number; credit: number; unrealized: number;
  pct_of_max_profit: number; days_held: number; risk_label: string;
}

function Skeleton() {
  return (
    <div>
      <div className="sk" style={{ height: 20, width: "40%", marginBottom: 8 }} />
      <div className="sk" style={{ height: 44, width: "65%", marginBottom: 8 }} />
      <div className="sk" style={{ height: 18, width: "45%", marginBottom: 16 }} />
      <div className="sk" style={{ height: 220, width: "100%", marginBottom: 16 }} />
      <div className="sk" style={{ height: 76, width: "100%", marginBottom: 10 }} />
      <div className="sk" style={{ height: 76, width: "100%" }} />
    </div>
  );
}

function HeroChart({ symbol, label }: { symbol: string; label: string }) {
  const [range, setRange] = useState<(typeof RANGES)[number]>(RANGES[2]); // 1M default
  const [scrub, setScrub] = useState<{ t: number; c: number } | null>(null);
  const q = useApi<{ symbol: string; price: number; chg_pct: number; bars: { t: number; c: number }[] }>(
    `/api/quote/${symbol}?range=${range.param}`
  );
  const bars = q.data?.bars ?? [];
  const shown = scrub ?? (bars.length ? bars[bars.length - 1] : null);
  const first = bars[0]?.c, last = bars[bars.length - 1]?.c;
  const trendUp = last != null && first != null ? last >= first : true;

  return (
    <div>
      <LivePrice symbol={symbol}/>
      <div className="hero-label">{label}</div>
      <div className="hero-value">{shown ? money(shown.c) : <span className="dim">—</span>}</div>
      <div className={`hero-sub ${scrub ? "" : cls(q.data?.chg_pct ?? (trendUp ? 1 : -1))}`}>
        {scrub ? (
          <span className="muted">
            {new Date(scrub.t * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
          </span>
        ) : q.data ? (
          <>
            {moneySigned((q.data.chg_pct / 100) * (q.data.price / (1 + q.data.chg_pct / 100)))}
            <span className="pct"> ({pctPts(q.data.chg_pct)}) {range.key}</span>
          </>
        ) : (
          <span className="dim">loading…</span>
        )}
      </div>
      <div style={{ marginTop: 6, minHeight: 220 }}>
        {bars.length > 1 ? (
          <Suspense fallback={<div className="sk" style={{ height: 220 }} />}>
            <Chart bars={bars} height={220} onScrub={setScrub} fmtPrice={(v) => money(v)} />
          </Suspense>
        ) : (
          <div className="sk" style={{ height: 220 }} />
        )}
      </div>
      <div className="ranges" role="tablist" aria-label="Chart range">
        {RANGES.map((r) => (
          <button
            key={r.key}
            role="tab"
            aria-selected={r.key === range.key}
            className={`range-btn${r.key === range.key ? " active" : ""}`}
            onClick={() => { setRange(r); setScrub(null); }}
          >
            {r.key}
          </button>
        ))}
      </div>
      <div className="caption">{symbol} · {range.key} · {bars.length} points{q.demo ? " · demo data" : ""}</div>
    </div>
  );
}

const positionMetrics = { unrealized: "Total gain/loss", day_pnl: "Today’s gain/loss", return_pct: "Percent change", equity: "Total equity" };
type PositionMetric = keyof typeof positionMetrics;

function PositionCard({ p, metric }: { p: Position; metric: PositionMetric }) {
  const value = p[metric];
  const [open, setOpen] = useState(false);
  return (
    <div className="card" onClick={() => setOpen((o) => !o)} role="button" aria-expanded={open} tabIndex={0}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(o => !o); } }}>
      <div className="card-row">
        <div>
          <div className="sym">{p.underlying}</div>
          <div className="strat">{p.display_name}</div>
        </div>
        <div>
          <div className={`pnl ${metric === "equity" ? "" : cls(value)}`}>{metric === "return_pct" ? pctPts(value) : metric === "equity" ? money(value) : moneySigned(value)}</div>
          <div className="meta"><span className="badge">{p.dte} DTE</span></div>
        </div>
      </div>
      <div className="meta" style={{ marginTop: 10 }}>
        Expiration: {p.expiry ? fmtDate(p.expiry) : "Not recorded"}
      </div>
      {p.legs?.length ? p.legs.map((leg, i) => (
        <div className="meta" key={i} style={{ marginTop: 4 }}>
          {leg.side === "sell" ? "Sell" : leg.side === "buy" ? "Buy" : "—"} {leg.quantity ?? "—"} · {leg.option_type ?? "Option"} · Strike {money(leg.strike)}
          {leg.expiry && <> · Exp {fmtDate(leg.expiry)}</>}
        </div>
      )) : <div className="meta">Strike: Not recorded</div>}
      {open && (
        <div className="detail-grid">
          <div className="detail-cell"><div className="k">Credit</div><div className="v">{money(p.credit)}</div></div>
          <div className="detail-cell"><div className="k">Max profit</div><div className="v">{pctPts(p.pct_of_max_profit, 0)}</div></div>
          <div className="detail-cell"><div className="k">Qty</div><div className="v">{p.qty}</div></div>
          <div className="detail-cell"><div className="k">Held</div><div className="v">{p.days_held}d</div></div>
          <div className="detail-cell"><div className="k">Opened</div><div className="v" style={{ fontSize: 13 }}>{fmtDate(p.opened_at)}</div></div>
          <div className="detail-cell"><div className="k">Risk</div><div className="v" style={{ fontSize: 13 }}>{p.risk_label || "—"}</div></div>
        </div>
      )}
    </div>
  );
}

export default function Home() {
  const [metric, setMetric] = useState<PositionMetric>("unrealized");
  const s = useApi<Summary>("/api/portfolio/summary");
  const pos = useApi<{ positions: Position[] } | Position[]>("/api/portfolio/positions");
  // The API wraps the list ({positions: [...]}) while demo data is a bare array.
  const positions = useMemo(() => {
    const d = pos.data;
    return Array.isArray(d) ? d : d?.positions ?? [];
  }, [pos.data]);

  // Headline chart: largest position's underlying, else SPY benchmark.
  const heroSym = positions.length
    ? [...positions].sort((a, b) => (b.qty || 0) - (a.qty || 0))[0].underlying
    : "SPY";
  const heroLabel = positions.length
    ? `${heroSym} · underlying of your largest position`
    : "SPY · market benchmark";

  if (s.loading && !s.data) return <Skeleton />;

  return (
    <div>
      {(s.error || pos.error) && <div className="notice" role="alert">{s.error || pos.error} <button onClick={()=>{s.refresh();pos.refresh();}}>Retry</button></div>}
      {(s.demo || pos.demo) && <span className="demo-pill">DEMO DATA</span>}
      <div className="hero-label">Account value</div>
      <div className="hero-value">{money(s.data?.account_value)}</div>
      <div className={`hero-sub ${cls(s.data?.day_pnl)}`}>
        {moneySigned(s.data?.day_pnl)} <span className="pct">({pctPts(s.data?.day_pnl_pct)}) today</span>
      </div>

      <div style={{ marginTop: 18 }}>
        <HeroChart symbol={heroSym} label={heroLabel} />
      </div>

      <div className="section-title">Positions
        <span className="badge">{s.data?.open_positions ?? positions.length} open</span>
      </div>
      <label className="meta" style={{ display: "block", marginBottom: 10 }}>
        Display <select aria-label="Position value display" value={metric} onChange={e => setMetric(e.target.value as PositionMetric)}>
          {Object.entries(positionMetrics).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select>
      </label>
      <div className="caption" style={{ marginBottom: 10 }}>
        {metric === "day_pnl" ? "Unavailable: prior-day option marks have not been recorded."
          : metric === "return_pct" ? "Gain/loss as a percentage of opening premium, using saved marks."
          : metric === "equity" ? "Saved net option value; short positions are liabilities. Excludes collateral and underlying shares."
          : "Open-position gain/loss using saved marks, not live quotes."}
      </div>
      {pos.loading && !positions.length ? (
        <><div className="sk" style={{ height: 76, marginBottom: 10 }} /><div className="sk" style={{ height: 76 }} /></>
      ) : positions.length === 0 ? (
        <div className="empty">No open positions.<br />Paper-trade from the desktop dashboard to see them here.</div>
      ) : (
        positions.map((p) => <PositionCard key={p.id} p={p} metric={metric} />)
      )}
      {s.data && (
        <div className="caption">
          Buying power {money(s.data.buying_power)} · Total P&L {moneySigned(s.data.total_pnl)}
          {s.stale ? " · quotes may be stale" : ""}
        </div>
      )}
    </div>
  );
}
