import { useApi } from "../lib/api";
import { cls, money, pctPts } from "../lib/fmt";

interface CelebMove {
  rank: number | null; symbol: string; company: string; investor: string;
  what_changed: string; period: string; why: string; heat: number;
  live_price: number | null; live_chg_pct: number | null;
}
interface EarnRow { symbol: string; company: string; earnings_date: string; when: string; status: string; }
interface VolRow {
  symbol: string; company: string; last: number | null; chg_1d_pct: number | null;
  chg_5d_pct: number | null; vol_20d_ann_pct: number | null; max_1d_move_10d_pct: number | null;
  atr14_pct: number | null; volatile: boolean; reasons: string[];
}
interface Candidate {
  symbol: string; company: string; strategy: string; display_name: string;
  dte: number; bias: string; credit_status: string; rationale: string;
}

function SkList({ n = 3, h = 84 }: { n?: number; h?: number }) {
  return (
    <div>{Array.from({ length: n }).map((_, i) => (
      <div key={i} className="sk" style={{ height: h, marginBottom: 10 }} />
    ))}</div>
  );
}

function CelebCard({ m }: { m: CelebMove }) {
  return (
    <div className="card">
      <div className="card-row">
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="sym">{m.symbol} <span className="muted" style={{ fontWeight: 500, fontSize: 13 }}>{m.company}</span></div>
          <div className="strat" style={{ marginTop: 4 }}>
            <strong style={{ color: "#fff" }}>{m.investor}</strong> — {m.what_changed}
          </div>
          <div className="t3 dim" style={{ fontSize: 12, marginTop: 3 }}>{m.period}</div>
          <div className="t2 muted" style={{ fontSize: 12.5, marginTop: 6, lineHeight: 1.45 }}>{m.why}</div>
        </div>
        <div style={{ textAlign: "right", flexShrink: 0 }}>
          {m.rank != null && <div className="heat">🔥 {m.heat}</div>}
          <div className="r1" style={{ fontSize: 14, marginTop: 4 }}>{m.live_price != null ? money(m.live_price) : "—"}</div>
          <div className={`r2 ${cls(m.live_chg_pct)}`} style={{ fontSize: 12 }}>{pctPts(m.live_chg_pct)}</div>
        </div>
      </div>
    </div>
  );
}

export default function Discover() {
  const celeb = useApi<{ scan_date: string; moves: CelebMove[] }>("/api/insights/celebrity");
  const earn = useApi<{ as_of: string; fresh: boolean; rows: EarnRow[] }>("/api/insights/earnings");
  const vol = useApi<{ as_of: string; fresh: boolean; rows: VolRow[] }>("/api/insights/volatility");
  const cand = useApi<Candidate[]>("/api/candidates");
  const anyDemo = celeb.demo || earn.demo || vol.demo || cand.demo;

  const earnRows = (earn.data?.rows ?? []).filter((r) => r.status === "Upcoming" || r.status === "Just reported");
  const earnIdle = (earn.data?.rows ?? []).filter((r) => r.status !== "Upcoming" && r.status !== "Just reported");
  const volRows = [...(vol.data?.rows ?? [])].sort(
    (a, b) => (b.max_1d_move_10d_pct ?? 0) - (a.max_1d_move_10d_pct ?? 0)
  );

  return (
    <div>
      <div className="screen-title">Discover</div>
      {anyDemo && <div style={{ marginTop: 8 }}><span className="demo-pill">DEMO DATA</span></div>}

      <div className="section-title">Top candidates</div>
      {cand.loading && !cand.data ? (
        <div className="sk" style={{ height: 150 }} />
      ) : (cand.data ?? []).length === 0 ? (
        <div className="empty">No candidates right now.</div>
      ) : (
        <div className="rail">
          {(cand.data ?? []).map((c) => (
            <div className="rail-card" key={c.symbol + c.strategy}>
              <div className="sym">{c.symbol}</div>
              <div className="co">{c.company}</div>
              <span className="badge">{c.display_name}</span>{" "}
              <span className="badge">{c.dte} DTE</span>
              <div className="why">{c.rationale}</div>
              <div className="caption" style={{ marginTop: 8 }}>{c.bias} · {c.credit_status}</div>
            </div>
          ))}
        </div>
      )}

      <div className="section-title">⭐ Celebrity moves</div>
      <div className="section-sub">What famous investors and funds just did — context, not trade signals.</div>
      {celeb.loading && !celeb.data ? <SkList /> :
        (celeb.data?.moves ?? []).map((m, i) => <CelebCard key={`${m.symbol}-${i}`} m={m} />)}

      <div className="section-title">📅 Earnings radar</div>
      {earn.loading && !earn.data ? <SkList n={4} h={64} /> : (
        <>
          {earnRows.map((r) => (
            <div className="irow" key={r.symbol}>
              <div className="avatar green">{r.symbol.slice(0, 2)}</div>
              <div className="grow">
                <div className="t1">{r.symbol} <span className="muted" style={{ fontWeight: 500, fontSize: 13 }}>{r.company}</span></div>
                <div className="t2">{r.earnings_date}</div>
              </div>
              <div className="right">
                <span className={`pill ${r.status === "Upcoming" ? "soon" : "done"}`}>{r.when}</span>
              </div>
            </div>
          ))}
          {earnIdle.length > 0 && (
            <div className="caption" style={{ marginTop: 10 }}>
              Also tracked: {earnIdle.map((r) => `${r.symbol} (${r.earnings_date})`).join(" · ")}
            </div>
          )}
          {earnRows.length === 0 && earnIdle.length === 0 && <div className="empty">No earnings dates available.</div>}
        </>
      )}

      <div className="section-title">🌊 Volatility watch</div>
      <div className="section-sub">⚡ = flagged: ≥5% day in last 10 sessions, ±4% last session, 20d vol ≥60%, or ATR ≥4%.</div>
      {vol.loading && !vol.data ? <SkList n={4} h={92} /> : (
        volRows.map((r) => (
          <div className="irow" key={r.symbol} style={{ alignItems: "flex-start" }}>
            <div className={`avatar ${r.volatile ? "red" : ""}`}>{r.volatile ? "⚡" : r.symbol.slice(0, 2)}</div>
            <div className="grow">
              <div className="t1">{r.symbol} <span className="muted" style={{ fontWeight: 500, fontSize: 13 }}>{r.company}</span></div>
              <div className="t2">
                <span className={cls(r.chg_1d_pct)} style={{ fontWeight: 700 }}>{pctPts(r.chg_1d_pct)}</span>
                <span className="dim"> today · </span>{r.last != null ? money(r.last) : "—"}
              </div>
              {r.volatile && r.reasons.length > 0 && (
                <div className="chips">{r.reasons.map((x, i) => <span className="chip" key={i}>{x}</span>)}</div>
              )}
            </div>
            <div className="right">
              <div className="r1">{r.vol_20d_ann_pct != null ? `${r.vol_20d_ann_pct.toFixed(1)}%` : "—"}</div>
              <div className="r2 dim">20d vol</div>
            </div>
          </div>
        ))
      )}
      <div className="caption">Insights update every few hours from market data. Educational context only — not trade signals.</div>
    </div>
  );
}
