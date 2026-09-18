import { useEffect, useRef, useState } from "react";
import {
  company, demoActivity, demoCandidates, demoCelebrity, demoEarnings,
  demoPositions, demoQuote, demoSummary, demoVolatility,
} from "./demo";

/**
 * API layer: same-origin /api/* with in-memory + localStorage cache,
 * stale-while-revalidate, and graceful demo fallback when the backend
 * is unreachable. Never throws to components; never a blank screen.
 */

const TTL: Record<string, number> = {
  "/api/health": 30e3,
  "/api/portfolio/summary": 30e3,
  "/api/portfolio/positions": 60e3,
  "/api/portfolio/activity": 120e3,
  "/api/insights/celebrity": 300e3,
  "/api/insights/earnings": 300e3,
  "/api/insights/volatility": 300e3,
  "/api/candidates": 300e3,
  "/api/quote": 60e3,
};

const mem = new Map<string, { ts: number; data: any }>();
const API_DOWN_KEY = "pulse:api-down";

function ttlFor(path: string): number {
  for (const k of Object.keys(TTL)) if (path.startsWith(k)) return TTL[k];
  return 60e3;
}
function cacheKey(path: string) { return "pulse:cache:" + path; }

function readCache(path: string): { ts: number; data: any } | null {
  const m = mem.get(path);
  if (m) return m;
  try {
    const raw = localStorage.getItem(cacheKey(path));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    mem.set(path, parsed);
    return parsed;
  } catch { return null; }
}

function writeCache(path: string, data: any) {
  const entry = { ts: Date.now(), data };
  mem.set(path, entry);
  try { localStorage.setItem(cacheKey(path), JSON.stringify(entry)); } catch { /* quota */ }
}

async function fetchJson(path: string, timeoutMs = 8000): Promise<any> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  // The app may be served from / (local dev) or /pulse (public tunnel).
  let base = "";
  try {
    const p = window.location.pathname;
    if (p === "/pulse" || p.startsWith("/pulse/")) base = "/pulse";
  } catch { /* ignore */ }
  try {
    const res = await fetch(base + path, { signal: ctrl.signal, headers: { accept: "application/json" } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally { clearTimeout(t); }
}

let apiDown: boolean | null = null;
function apiDownCached(): boolean {
  if (apiDown !== null) return apiDown;
  try {
    const raw = localStorage.getItem(API_DOWN_KEY);
    if (!raw) return false;
    const { ts, down } = JSON.parse(raw);
    if (Date.now() - ts < 60e3) { apiDown = down; return down; }
  } catch { /* ignore */ }
  return false;
}
function setApiDown(down: boolean) {
  apiDown = down;
  try { localStorage.setItem(API_DOWN_KEY, JSON.stringify({ ts: Date.now(), down })); } catch { /* ignore */ }
}

/** Demo data per endpoint when the API is unreachable. */
function demoFor(path: string): any {
  if (path === "/api/portfolio/summary") return demoSummary();
  if (path === "/api/portfolio/positions") return demoPositions();
  if (path === "/api/portfolio/activity") return demoActivity();
  if (path === "/api/insights/celebrity") return demoCelebrity();
  if (path === "/api/insights/earnings") return demoEarnings();
  if (path === "/api/insights/volatility") return demoVolatility();
  if (path === "/api/candidates") return demoCandidates();
  const q = path.match(/^\/api\/quote\/([^?]+)\??.*?(?:range=([^&]+))?/);
  if (q) return demoQuote(decodeURIComponent(q[1]), q[2] || "1d");
  return null;
}

export interface ApiState<T> {
  data: T | null;
  loading: boolean;
  demo: boolean;
  stale: boolean;
  refresh: () => void;
}

export function useApi<T>(path: string | null, opts?: { timeoutMs?: number }): ApiState<T> {
  const [state, setState] = useState<ApiState<T>>(() => {
    if (!path) return { data: null, loading: false, demo: false, stale: false, refresh: () => {} };
    const c = readCache(path);
    return {
      data: (c?.data ?? null) as T | null,
      loading: !c,
      demo: false,
      stale: !!c && Date.now() - c.ts > ttlFor(path),
      refresh: () => {},
    };
  });
  const nonce = useRef(0);

  const load = (background: boolean) => {
    if (!path) return;
    const n = ++nonce.current;
    const cached = readCache(path);
    const ttl = ttlFor(path);
    const freshEnough = cached && Date.now() - cached.ts < ttl;
    if (freshEnough && !background) return; // already have fresh data
    if (!background) setState(s => ({ ...s, loading: !cached }));

    (async () => {
      // Fast path: API known down recently -> demo immediately.
      if (apiDownCached() && !cached) {
        if (nonce.current === n)
          setState(s => ({ ...s, data: (demoFor(path) as T), loading: false, demo: true, stale: false, refresh: s.refresh }));
        return;
      }
      try {
        const data = await fetchJson(path, opts?.timeoutMs);
        setApiDown(false);
        writeCache(path, data);
        if (nonce.current === n)
          setState(s => ({ ...s, data, loading: false, demo: false, stale: false, refresh: s.refresh }));
      } catch {
        if (nonce.current !== n) return;
        if (cached) {
          // Keep stale data visible; mark stale, retry demo only if nothing at all.
          setState(s => ({ ...s, loading: false, stale: true, refresh: s.refresh }));
          // One cheap health probe to decide demo mode for other endpoints.
          fetchJson("/api/health", 2500).then(() => setApiDown(false)).catch(() => setApiDown(true));
        } else {
          setApiDown(true);
          setState(s => ({ ...s, data: (demoFor(path) as T), loading: false, demo: true, stale: false, refresh: s.refresh }));
        }
      }
    })();
  };

  useEffect(() => {
    if (!path) return;
    load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);

  const refresh = () => load(true);
  // keep refresh stable-ish in returned object
  return { ...state, refresh };
}

/** Find a company's display name for a symbol (API data preferred, demo map fallback). */
export function companyName(sym: string, fromApi?: string | null): string {
  if (fromApi) return fromApi;
  return company(sym);
}

/** Range definitions for the quote chart. */
export const RANGES = [
  { key: "1D", param: "1d" },
  { key: "1W", param: "5d" },
  { key: "1M", param: "1mo" },
  { key: "3M", param: "3mo" },
  { key: "1Y", param: "1y" },
] as const;
