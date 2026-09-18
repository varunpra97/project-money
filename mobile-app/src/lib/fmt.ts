const usd0 = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});
const usdSigned = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
  signDisplay: "exceptZero",
});
const usdCompact = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});
const pct1 = new Intl.NumberFormat("en-US", {
  style: "percent",
  maximumFractionDigits: 2,
  signDisplay: "exceptZero",
});
const pctPlain = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  signDisplay: "exceptZero",
});
const num0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export const money = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? "—" : usd0.format(v);
export const moneySigned = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? "—" : usdSigned.format(v);
export const moneyCompact = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? "—" : usdCompact.format(v);
export const pct = (frac: number | null | undefined) =>
  frac == null || Number.isNaN(frac) ? "—" : pct1.format(frac);
/** percent-points value like 2.43 -> "+2.43%" */
export const pctPts = (v: number | null | undefined, digits = 2) =>
  v == null || Number.isNaN(v)
    ? "—"
    : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(digits)}%`;
export const int = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? "—" : num0.format(v);
export const num1 = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? "—" : pctPlain.format(v);

export const cls = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? "" : v > 0 ? "up" : v < 0 ? "down" : "";

export function timeAgo(ts: string | number): string {
  const t = typeof ts === "number" ? ts : Date.parse(ts);
  if (Number.isNaN(t)) return "";
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  const d = Math.floor(s / 86400);
  return d === 1 ? "yesterday" : `${d}d ago`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length <= 10 ? iso + "T12:00:00" : iso);
  return Number.isNaN(+d)
    ? iso
    : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
