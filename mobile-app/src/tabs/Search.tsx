import { lazy, Suspense, useState } from "react";
import { RANGES, useApi } from "../lib/api";
import { cls, fmtDate, money, moneySigned, pctPts } from "../lib/fmt";

const Chart = lazy(() => import("../components/Chart"));

interface VolRow {
  symbol: string; company: string; last: number | null; chg_1d_pct: number | null;
  chg_5d_pct: number | null; vol_20d_ann_pct: number | null; max_1d_move_10d_pct: number | null;
  atr14_pct: number | null; volatile: boolean; reasons: string[];
}
interface EarnRow { symbol: string; company: string; earnings_date: string; when: string; status: string; }

export default function Search() {
  const [input, setInput] = useState("");
  const [symbol, setSymbol] = useState<string | null>(null);
  const [range, setRange] = useState<(typeof RANGES)[number]>(RANGES[0]);
  const [scrub, setScrub] = useState<{ t: number; c: number } | null>(null);

  const q = useApi<{ symbol: string; price: number; chg_pct: number; bars: { t: number; c: number }[] }>(
    symbol ? `/api/quote/${symbol}?range=${range.param}` : null
  );
  const vol = useApi<{ rows: VolRow[] }>("/api/insights/volatility");
  const earn = useApi<{ rows: EarnRow[] }>("/api/insights/earnings");

  const submit = () => {
    const s = input.trim().toUpperCase().replace(/[^A-Z.\-]/g, "");
    if (s) { setSymbol(s); setScrub(null); }
  };

  const vrow = symbol ? (vol.data?.rows ?? []).find((r) => r.symbol.toUpperCase() === symbol) : undefined;
  const erow = symbol ? (earn.data?.rows ?? []).find((r) => r.symbol.toUpperCase() === symbol) : undefined;
  const bars = q.data?.bars ?? [];
  const shown = scrub ?? (bars.length ? bars[bars.length - 1] : null);

  return (
    <div>
      <div className="screen-title">Search</div>
      <form className="searchbar" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Symbol — try TEM, BE, META"
          autoCapitalize="characters"
          autoCorrect="off"
          spellCheck={false}
          aria-label="Symbol lookup"
        />
        <button type="submit">Go</button>
      </form>
      {(q.demo || vol.demo) && symbol && <span className="demo-pill">DEMO DATA</span>}

      {!symbol ? (
        <div className="empty">
          Look up any ticker for a live quote, chart,<br />volatility stats and earnings status.
        </div>
      ) : q.loading && !q.data ? (
        <><div className="sk" style={{ height: 90, marginBottom: 12 }} /><div className="sk" style={{ height: 220, marginBottom: 12 }} /><div className="sk" style={{ height: 120 }} /></>
      ) : !q.data || bars.length < 2 ? (
        <div className="empty">No quote for {symbol}.{q.demo ? " (demo universe is limited)" : " Check the symbol and try again."}</div>
      ) : (
        <div className="quote-head">
          <div className="sym">{q.data.symbol}</div>
          <div className="co">{vrow?.company ?? erow?.company ?? ""}</div>
          <div className="px">{shown ? money(shown.c) : "—"}</div>
          <div className={`chg ${scrub ? "" : cls(q.data.chg_pct)}`}>
            {scrub
              ? new Date(scrub.t).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
              : <>{moneySigned(q.data.price - q.data.price / (1 + q.data.chg_pct / 100))} ({pctPts(q.data.chg_pct)}) {range.key}</>}
          </div>

          <div style={{ marginTop: 8, minHeight: 220 }}>
            <Suspense fallback={<div className="sk" style={{ height: 220 }} />}>
              <Chart bars={bars} height={220} onScrub={setScrub} fmtPrice={(v) => money(v)} />
            </Suspense>
          </div>
          <div className="ranges">
            {RANGES.map((r) => (
              <button key={r.key} className={`range-btn${r.key === range.key ? " active" : ""}`}
                onClick={() => { setRange(r); setScrub(null); }}>
                {r.key}
              </button>
            ))}
          </div>

          <div className="section-title" style={{ marginTop: 18 }}>Key stats</div>
          <div className="stat-grid">
            <div className="stat"><div className="k">20d vol (ann.)</div><div className="v">{vrow?.vol_20d_ann_pct != null ? `${vrow.vol_20d_ann_pct.toFixed(1)}%` : "—"}</div></div>
            <div className="stat"><div className="k">Max 1d (10d)</div><div className="v">{vrow?.max_1d_move_10d_pct != null ? pctPts(vrow.max_1d_move_10d_pct) : "—"}</div></div>
            <div className="stat"><div className="k">ATR(14)</div><div className="v">{vrow?.atr14_pct != null ? `${vrow.atr14_pct.toFixed(2)}%` : "—"}</div></div>
            <div className="stat"><div className="k">5d move</div><div className={`v ${cls(vrow?.chg_5d_pct)}`}>{pctPts(vrow?.chg_5d_pct)}</div></div>
          </div>

          <div className="card" style={{ cursor: "default" }}>
            <div className="card-row">
              <div>
                <div className="sym" style={{ fontSize: 15 }}>📅 Earnings</div>
                <div className="strat">{erow ? `${fmtDate(erow.earnings_date)}` : "No date on file"}</div>
              </div>
              {erow && <span className={`pill ${erow.status === "Upcoming" ? "soon" : erow.status === "Just reported" ? "done" : "idle"}`}>{erow.when}</span>}
            </div>
          </div>

          {vrow?.volatile && vrow.reasons.length > 0 && (
            <div className="card" style={{ cursor: "default" }}>
              <div className="sym" style={{ fontSize: 15, marginBottom: 4 }}>⚡ Volatility flags</div>
              <div className="chips">{vrow.reasons.map((x, i) => <span className="chip" key={i}>{x}</span>)}</div>
            </div>
          )}
          <div className="caption">Quotes delayed · educational context only.</div>
        </div>
      )}
    </div>
  );
}
