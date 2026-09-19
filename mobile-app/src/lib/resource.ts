import { useEffect, useState } from "react";
export function useResource<T>(path: string, interval = 60000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setData(null); setLoading(true); setError("");
    async function load() {
      try {
        const base = location.pathname.startsWith("/pulse") ? "/pulse" : "";
        const res = await fetch(base + path + (version > 0 ? (path.includes("?") ? "&" : "?") + "refresh=true" : ""), { signal: controller.signal, cache: "no-store" });
        if (!res.ok) throw new Error("The service is unavailable. Please retry.");
        const body = await res.json();
        if (body.error) throw new Error(body.error);
        if (active) { setData(body); setError(""); }
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : "Could not load data.");
      } finally { if (active) setLoading(false); }
    }
    load();
    const timer = window.setInterval(load, interval);
    return () => { active = false; controller.abort(); clearInterval(timer); };
  }, [path, version, interval]);
  return { data, error, loading, refresh: () => setVersion(v => v + 1) };
}
