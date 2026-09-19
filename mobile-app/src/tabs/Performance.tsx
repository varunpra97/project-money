import { useState } from "react";
import { useResource } from "../lib/resource";
import { money, moneySigned, fmtDate } from "../lib/fmt";
interface PerformanceData {
  period: string; as_of: string; pnl: number | null; realized: number; unrealized: number;
  closed_trades: number; win_rate: number | null; average_win: number | null; average_loss: number | null;
  best_trade: number | null; worst_trade: number | null; profit_factor: number | null;
  open_positions: number; premium: number; history_since: string;
  curve: {ts: string; pnl: number}[]; curve_label: string;
  strategies: {strategy: string; trades: number; realized: number}[]; notes: string[];
}
const PERIODS = [["lifetime", "Lifetime"], ["week", "1 week"], ["month", "1 month"], ["quarter", "Quarter"]];
function PnlChart({ points }: { points: PerformanceData["curve"] }) {
  if (points.length < 2) return <div className="history-empty"><span>◷</span><h3>Your history starts here</h3><p>Snapshots are recorded while the backend runs. A curve appears after the next observation.</p></div>;
  const values = points.map(p => p.pnl), lo = Math.min(...values), hi = Math.max(...values);
  const first = Date.parse(points[0].ts), span = Date.parse(points[points.length-1].ts)-first || 1;
  const coords = points.map(p => `${16+(Date.parse(p.ts)-first)/span*568},${155-(p.pnl-lo)/(hi-lo || 1)*130}`).join(" ");
  return <figure className="performance-chart"><svg viewBox="0 0 600 180" role="img" aria-label={`Observed P&L from ${money(points[0].pnl)} to ${money(points[points.length-1].pnl)}`}><line x1="16" x2="584" y1="155" y2="155" stroke="#333"/><polyline points={coords} fill="none" stroke="#6ce9a6" strokeWidth="3" strokeLinejoin="round"/></svg><figcaption><span>{fmtDate(points[0].ts)}</span><span>{money(lo)} – {money(hi)}</span><span>{fmtDate(points[points.length-1].ts)}</span></figcaption></figure>;
}
export default function Performance() {
  const [period, setPeriod] = useState("lifetime");
  const {data: d, error, loading, refresh} = useResource<PerformanceData>(`/api/performance?period=${period}`);
  return <div className="insight-page">
    <header className="page-heading"><div><div className="eyebrow">YOUR PAPER PORTFOLIO</div><h1>Performance</h1></div><button className="subtle-button" onClick={refresh}>Refresh</button></header>
    <div className="segment" role="group" aria-label="Performance period">{PERIODS.map(([k,v])=><button key={k} aria-pressed={period===k} className={period===k?"selected":""} onClick={()=>setPeriod(k)}>{v}</button>)}</div>
    {error && <div className="notice" role="alert">{error} <button onClick={refresh}>Retry</button></div>}
    {loading && !d && <div className="sk" style={{height:260}}/>}
    {d && <>
      <section className="pnl-hero"><div className="eyebrow">{period === "lifetime" ? "LIFETIME" : "PERIOD"} TOTAL P&L</div><div className={`pnl-number ${(d.pnl ?? 0)<0?"down":"up"}`}>{moneySigned(d.pnl)}</div><p>{d.pnl === null ? "Not enough historical marks for this period" : "Realized results + change in unrealized P&L"}</p><div className="hero-foot"><span>{d.open_positions} positions open now</span><span>Paper · saved marks</span></div></section>
      <div className="metric-grid">{[["Realized P&L",moneySigned(d.realized)],["Unrealized · now",moneySigned(d.unrealized)],["Opening premiums",money(d.premium)],["Closed trades",d.closed_trades],["Win rate",d.win_rate===null?"—":`${d.win_rate}%`],["Profit factor",d.profit_factor===null?"—":d.profit_factor.toFixed(2)]].map(([k,v])=><div className="metric" key={k}><span>{k}</span><strong>{v}</strong></div>)}</div>
      <section className="panel"><h2>{d.curve_label}</h2><PnlChart points={d.curve}/><p className="caption">Observations since {fmtDate(d.history_since)}. Gaps connect recorded points; missing periods are not reconstructed.</p></section>
      <section className="panel"><h2>Trade quality</h2><div className="quality-grid">{[["Average winner",d.average_win],["Average loser",d.average_loss],["Best close",d.best_trade],["Worst close",d.worst_trade]].map(([k,v])=><div key={String(k)}><span>{k}</span><strong>{moneySigned(v as number|null)}</strong></div>)}</div><p className="caption">Based on recorded closed trades in this window. Win rate includes flat closes; profit factor needs at least one losing trade. Premiums are receipts, not profit.</p></section>
      <section className="panel"><h2>Results by strategy</h2>{d.strategies.length ? d.strategies.map(s=><div className="strategy-row" key={s.strategy}><div>{s.strategy}<small>{s.trades} closed trades</small></div><strong className={s.realized<0?"down":"up"}>{moneySigned(s.realized)}</strong></div>):<p className="caption">No dated closed trades in this period yet.</p>}</section>
      <details className="data-notes" open><summary>About these numbers</summary>{d.notes.map(n=><p key={n}>{n}</p>)}<p>Updated {new Date(d.as_of).toLocaleString()}</p></details>
    </>}
  </div>;
}
