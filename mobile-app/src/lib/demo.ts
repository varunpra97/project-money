/**
 * Demo fallback data used when the /api backend is unreachable.
 * Values mirror the real tracker universe so the UI looks and behaves
 * identically; the app shows a "Demo" pill whenever this is active.
 */

export interface Bar { t: number; c: number }

function hashStr(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(seed: number) {
  let a = seed;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const BASE_PX: Record<string, number> = {
  AAPL: 262.4, META: 665.75, AMZN: 253.71, GOOGL: 248.9, NFLX: 1185.2,
  SPCX: 152.71, TEM: 77.84, BE: 265.63, CBRS: 198.37, UBER: 96.4,
  INTC: 38.2, HD: 402.5, VST: 178.3, FDXF: 24.6, V: 348.1, MA: 592.7,
  SPGI: 512.4, AVGO: 348.9, SPY: 648.2, QQQ: 592.1, NVDA: 188.4, TSLA: 428.6,
};

const RANGE_POINTS: Record<string, number> = {
  "1d": 78, "5d": 78 * 5, "1mo": 22, "3mo": 66, "1y": 252,
};
const RANGE_VOL: Record<string, number> = {
  "1d": 0.004, "5d": 0.006, "1mo": 0.016, "3mo": 0.02, "1y": 0.022,
};
const RANGE_STEP_MS: Record<string, number> = {
  "1d": 5 * 60e3, "5d": 30 * 60e3, "1mo": 86400e3, "3mo": 86400e3, "1y": 86400e3,
};

export function demoBars(symbol: string, range: string): Bar[] {
  const sym = symbol.toUpperCase();
  const n = RANGE_POINTS[range] ?? 78;
  const vol = RANGE_VOL[range] ?? 0.01;
  const step = RANGE_STEP_MS[range] ?? 86400e3;
  const rnd = mulberry32(hashStr(sym + ":" + range));
  const end = BASE_PX[sym] ?? 100 + (hashStr(sym) % 400);
  // random walk backwards from the end price so the latest bar is exact
  const rets: number[] = [];
  for (let i = 0; i < n - 1; i++) rets.push((rnd() - 0.485) * vol * 2);
  const closes: number[] = [end];
  for (let i = rets.length - 1; i >= 0; i--) closes.unshift(closes[0] / (1 + rets[i]));
  const now = Date.now();
  const startT = now - (n - 1) * step;
  return closes.map((c, i) => ({ t: startT + i * step, c: +c.toFixed(2) }));
}

export function demoQuote(symbol: string, range = "1d") {
  const bars = demoBars(symbol, range);
  const first = bars[0].c, last = bars[bars.length - 1].c;
  return {
    symbol: symbol.toUpperCase(),
    price: last,
    chg_pct: +(((last - first) / first) * 100).toFixed(2),
    bars,
  };
}

const COMPANIES: Record<string, string> = {
  SPCX: "SpaceX (pre-IPO tracker)", AMZN: "Amazon.com", GOOGL: "Alphabet",
  NFLX: "Netflix", META: "Meta Platforms", CBRS: "Cerebras Systems",
  HD: "Home Depot", INTC: "Intel", UBER: "Uber", VST: "Vistra",
  TEM: "Tempus AI", BE: "Bloom Energy", FDXF: "FedEx Freight",
  V: "Visa", MA: "Mastercard", SPGI: "S&P Global", AVGO: "Broadcom",
  AAPL: "Apple", SPY: "SPDR S&P 500",
};
export const company = (s: string) => COMPANIES[s.toUpperCase()] ?? s.toUpperCase();

const day = 86400e3;
const isoDay = (offsetDays: number) =>
  new Date(Date.now() + offsetDays * day).toISOString().slice(0, 10);

export const demoSummary = () => ({
  account_value: 51240.18,
  buying_power: 18420.55,
  day_pnl: 342.66,
  day_pnl_pct: 0.67,
  total_pnl: 1240.18,
  open_positions: 3,
  greeks: { delta: 12.4, theta: 8.2, vega: -45.1 },
  as_of: new Date().toISOString(),
});

export const demoPositions = () => [
  {
    id: "pos-aapl-csp", underlying: "AAPL", strategy: "cash_secured_put",
    display_name: "Cash-Secured Put", opened_at: new Date(Date.now() - 14 * day).toISOString(),
    dte: 32, qty: 1, credit: 320.0, unrealized: 144.0, pct_of_max_profit: 45.0,
    days_held: 14, risk_label: "Defined-ish",
  },
  {
    id: "pos-meta-csp", underlying: "META", strategy: "cash_secured_put",
    display_name: "Cash-Secured Put", opened_at: new Date(Date.now() - 6 * day).toISOString(),
    dte: 21, qty: 1, credit: 275.0, unrealized: 96.25, pct_of_max_profit: 35.0,
    days_held: 6, risk_label: "Defined-ish",
  },
  {
    id: "pos-spy-putspread", underlying: "SPY", strategy: "put_spread",
    display_name: "Put Spread", opened_at: new Date(Date.now() - 3 * day).toISOString(),
    dte: 18, qty: 2, credit: 410.0, unrealized: -38.5, pct_of_max_profit: -9.4,
    days_held: 3, risk_label: "Defined",
  },
];

export const demoActivity = () => [
  { ts: new Date(Date.now() - 2 * 3600e3).toISOString(), kind: "mark", text: "AAPL put marked up — position +$144 unrealized", amount: 144.0 },
  { ts: new Date(Date.now() - 26 * 3600e3).toISOString(), kind: "open", text: "Opened SPY put spread (18 DTE) for $410 credit", amount: 410.0 },
  { ts: new Date(Date.now() - 3 * day).toISOString(), kind: "open", text: "Opened META cash-secured put (21 DTE) for $275 credit", amount: 275.0 },
  { ts: new Date(Date.now() - 6 * day).toISOString(), kind: "close", text: "Closed META 480 put for $55 — kept $220 of $275", amount: 220.0 },
  { ts: new Date(Date.now() - 14 * day).toISOString(), kind: "open", text: "Opened AAPL cash-secured put (32 DTE) for $320 credit", amount: 320.0 },
];

export const demoCelebrity = () => ({
  scan_date: new Date().toISOString().slice(0, 10),
  moves: [
    { rank: 1, symbol: "BE", company: "Bloom Energy", investor: "Top 13F filer", what_changed: "New 2.1M-share position", period: "Q2 2026 13F", why: "Largest new AI-power bet in the scan; stock +9.6% max 1-day move in last 10 sessions.", heat: 100, live_price: 265.63, live_chg_pct: -5.39 },
    { rank: 2, symbol: "TEM", company: "Tempus AI", investor: "Growth fund cluster", what_changed: "Position +68% quarter over quarter", period: "Q2 2026 13F", why: "Healthcare-AI momentum name; 20-day realized vol 94.5% annualized.", heat: 92, live_price: 77.84, live_chg_pct: -3.14 },
    { rank: 3, symbol: "CBRS", company: "Cerebras Systems", investor: "Senate disclosure", what_changed: "$250k–$500k purchase disclosed", period: "Aug 2026 filing", why: "AI-chip IPO name drawing political-buyer interest.", heat: 84, live_price: 198.37, live_chg_pct: 2.18 },
    { rank: 4, symbol: "SPCX", company: "SpaceX (pre-IPO tracker)", investor: "Celebrity tech investor", what_changed: "Added on weakness", period: "Jul 2026 disclosure", why: "Pre-IPO proxy exposure; 5.15% max 1-day move recently.", heat: 71, live_price: 152.71, live_chg_pct: -1.36 },
    { rank: 5, symbol: "META", company: "Meta Platforms", investor: "Mega-cap fund rotation", what_changed: "Top-10 holding reiterated", period: "Q2 2026 13F", why: "Earnings 2026-10-28; 6.55% max 1-day move in last 10 sessions.", heat: 66, live_price: 665.75, live_chg_pct: -2.43 },
  ],
});

export const demoEarnings = () => ({
  as_of: new Date().toISOString(),
  fresh: true,
  rows: [
    { symbol: "TEM", company: "Tempus AI", earnings_date: isoDay(5), when: "in 5 days", status: "Upcoming" },
    { symbol: "BE", company: "Bloom Energy", earnings_date: isoDay(-3), when: "3 days ago", status: "Just reported" },
    { symbol: "GOOGL", company: "Alphabet", earnings_date: "2026-10-28", when: "—", status: "—" },
    { symbol: "META", company: "Meta Platforms", earnings_date: "2026-10-28", when: "—", status: "—" },
    { symbol: "AMZN", company: "Amazon.com", earnings_date: "2026-10-29", when: "—", status: "—" },
    { symbol: "SPCX", company: "SpaceX (pre-IPO tracker)", earnings_date: "2026-11-03", when: "—", status: "—" },
  ],
});

export const demoVolatility = () => ({
  as_of: new Date().toISOString(),
  fresh: true,
  rows: [
    { symbol: "TEM", company: "Tempus AI", last: 77.84, chg_1d_pct: -3.14, chg_5d_pct: 31.91, vol_20d_ann_pct: 94.5, max_1d_move_10d_pct: 14.85, atr14_pct: 6.1, volatile: true, reasons: ["≥5% single-day move in last 10 sessions", "20d realized vol ≥60% (ann.)", "ATR(14) ≥4% of price"] },
    { symbol: "BE", company: "Bloom Energy", last: 265.63, chg_1d_pct: -5.39, chg_5d_pct: -3.67, vol_20d_ann_pct: 74.2, max_1d_move_10d_pct: 9.63, atr14_pct: 6.74, volatile: true, reasons: ["≥5% single-day move in last 10 sessions", "±4% move in the last session", "20d realized vol ≥60% (ann.)"] },
    { symbol: "CBRS", company: "Cerebras Systems", last: 198.37, chg_1d_pct: 2.18, chg_5d_pct: 3.36, vol_20d_ann_pct: 72.1, max_1d_move_10d_pct: 10.3, atr14_pct: 6.16, volatile: true, reasons: ["≥5% single-day move in last 10 sessions", "20d realized vol ≥60% (ann.)", "ATR(14) ≥4% of price"] },
    { symbol: "SPCX", company: "SpaceX (pre-IPO tracker)", last: 152.71, chg_1d_pct: -1.36, chg_5d_pct: 2.4, vol_20d_ann_pct: 41.8, max_1d_move_10d_pct: 5.15, atr14_pct: 3.2, volatile: true, reasons: ["≥5% single-day move in last 10 sessions"] },
    { symbol: "META", company: "Meta Platforms", last: 665.75, chg_1d_pct: -2.43, chg_5d_pct: 1.8, vol_20d_ann_pct: 29.9, max_1d_move_10d_pct: 6.55, atr14_pct: 2.9, volatile: true, reasons: ["≥5% single-day move in last 10 sessions"] },
    { symbol: "AMZN", company: "Amazon.com", last: 253.71, chg_1d_pct: 1.0, chg_5d_pct: 2.2, vol_20d_ann_pct: 26.1, max_1d_move_10d_pct: 2.13, atr14_pct: 1.8, volatile: false, reasons: [] },
  ],
});

export const demoCandidates = () => [
  { symbol: "BE", company: "Bloom Energy", strategy: "put_spread", display_name: "Put Spread", dte: 30, bias: "Bullish", credit_status: "quote pending", rationale: "High IV rank with defined risk; earnings passed 3 days ago." },
  { symbol: "V", company: "Visa", strategy: "cash_secured_put", display_name: "Cash-Secured Put", dte: 45, bias: "Bullish", credit_status: "quote pending", rationale: "Low-volatility compounder; steady premium." },
  { symbol: "TEM", company: "Tempus AI", strategy: "iron_condor", display_name: "Iron Condor", dte: 21, bias: "Neutral", credit_status: "quote pending", rationale: "Elevated IV into earnings in 5 days; neutral premium capture." },
  { symbol: "HD", company: "Home Depot", strategy: "covered_call", display_name: "Covered Call", dte: 30, bias: "Neutral", credit_status: "quote pending", rationale: "Range-bound; overwrite for income." },
];
