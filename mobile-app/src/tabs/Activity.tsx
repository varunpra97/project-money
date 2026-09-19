import { useApi } from "../lib/api";
import { money, moneySigned, timeAgo } from "../lib/fmt";

interface Summary {
  account_value: number; buying_power: number; day_pnl: number; day_pnl_pct: number;
  total_pnl: number; open_positions: number; greeks: Record<string, number>; as_of: string;
}
interface Act { ts: string; kind: string; text: string; amount: number | null; }

const DOT: Record<string, string> = { open: "open", close: "close", mark: "mark" };

export default function Activity() {
  const s = useApi<Summary>("/api/portfolio/summary");
  const a = useApi<{ activity: Act[] } | Act[]>("/api/portfolio/activity");
  // The API wraps the list ({activity: [...]}) while demo data is a bare array.
  const items = Array.isArray(a.data) ? a.data : a.data?.activity ?? [];

  return (
    <div>
      {(s.error || a.error) && <div className="notice" role="alert">{s.error || a.error} <button onClick={()=>{s.refresh();a.refresh();}}>Retry</button></div>}
      <div className="screen-title">Activity</div>
      {(s.demo || a.demo) && <div style={{ marginTop: 8 }}><span className="demo-pill">DEMO DATA</span></div>}

      <div className="section-title" style={{ marginTop: 14 }}>Account</div>
      {s.loading && !s.data ? (
        <div className="sk" style={{ height: 120 }} />
      ) : (
        <div className="stat-grid">
          <div className="stat"><div className="k">Buying power</div><div className="v">{money(s.data?.buying_power)}</div></div>
          <div className="stat"><div className="k">Total P&L</div>
            <div className={`v ${(s.data?.total_pnl ?? 0) >= 0 ? "up" : "down"}`}>{moneySigned(s.data?.total_pnl)}</div>
          </div>
          <div className="stat"><div className="k">Account value</div><div className="v">{money(s.data?.account_value)}</div></div>
          <div className="stat"><div className="k">Open positions</div><div className="v">{s.data?.open_positions ?? "—"}</div></div>
        </div>
      )}

      <div className="section-title">History</div>
      {a.loading && !items.length ? (
        <><div className="sk" style={{ height: 56, marginBottom: 10 }} /><div className="sk" style={{ height: 56, marginBottom: 10 }} /><div className="sk" style={{ height: 56 }} /></>
      ) : items.length === 0 ? (
        <div className="empty">Nothing here yet.<br />Opens, closes and marks will appear in this feed.</div>
      ) : (
        items.map((it, i) => (
          <div className="feed-item" key={`${it.ts}-${i}`}>
            <div className={`feed-dot ${DOT[it.kind] ?? "close"}`} />
            <div className="ft">
              {it.text}
              <div className="fts">{timeAgo(it.ts)}</div>
            </div>
            {it.amount != null && (
              <div className={`fa ${it.amount >= 0 ? "up" : "down"}`}>{moneySigned(it.amount)}</div>
            )}
          </div>
        ))
      )}
      <div className="caption">Paper trading — no real money moves here.</div>
    </div>
  );
}
