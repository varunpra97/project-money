import { useEffect, useRef } from "react";

export interface CBar { t: number; c: number }

interface Props {
  bars: CBar[];
  height?: number;
  lineWidth?: number;
  /** called with scrubbed bar or null when scrub ends */
  onScrub?: (bar: CBar | null) => void;
  /** format a price for the floating label */
  fmtPrice?: (v: number) => string;
}

/**
 * Robinhood-style line chart: canvas, dpr-aware, gradient fill,
 * touch-scrub crosshair (vertical line + dot + floating price pill)
 * driven by rAF-throttled pointer events at 60fps.
 */
export default function Chart({ bars, height = 220, lineWidth = 2, onScrub, fmtPrice }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const scrubRef = useRef<number | null>(null);
  const rafRef = useRef(0);
  const barsRef = useRef(bars);
  barsRef.current = bars;
  const cbRef = useRef(onScrub);
  cbRef.current = onScrub;
  const fmtRef = useRef(fmtPrice);
  fmtRef.current = fmtPrice;

  const draw = () => {
    const canvas = canvasRef.current, wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const data = barsRef.current;
    const dpr = Math.min(3, window.devicePixelRatio || 1);
    const W = wrap.clientWidth, H = height;
    if (W <= 0 || data.length < 2) return;
    if (canvas.width !== Math.round(W * dpr) || canvas.height !== Math.round(H * dpr)) {
      canvas.width = Math.round(W * dpr);
      canvas.height = Math.round(H * dpr);
      canvas.style.width = `${W}px`;
      canvas.style.height = `${H}px`;
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);

    let min = Infinity, max = -Infinity;
    for (const b of data) { if (b.c < min) min = b.c; if (b.c > max) max = b.c; }
    if (min === max) { min *= 0.99; max *= 1.01; }
    const padY = (max - min) * 0.12;
    min -= padY; max += padY;

    const padL = 4, padR = 8, padT = 14, padB = 10;
    const iw = W - padL - padR, ih = H - padT - padB;
    const x = (i: number) => padL + (i / (data.length - 1)) * iw;
    const y = (v: number) => padT + (1 - (v - min) / (max - min)) * ih;

    const up = data[data.length - 1].c >= data[0].c;
    const color = up ? "#00C805" : "#FF5000";

    // area fill
    const grad = ctx.createLinearGradient(0, padT, 0, padT + ih);
    grad.addColorStop(0, up ? "rgba(0,200,5,0.22)" : "rgba(255,80,0,0.22)");
    grad.addColorStop(1, "rgba(0,0,0,0)");
    ctx.beginPath();
    ctx.moveTo(x(0), y(data[0].c));
    for (let i = 1; i < data.length; i++) ctx.lineTo(x(i), y(data[i].c));
    ctx.lineTo(x(data.length - 1), padT + ih);
    ctx.lineTo(x(0), padT + ih);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // line
    ctx.beginPath();
    ctx.moveTo(x(0), y(data[0].c));
    for (let i = 1; i < data.length; i++) ctx.lineTo(x(i), y(data[i].c));
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.stroke();

    const si = scrubRef.current;
    if (si != null && si >= 0 && si < data.length) {
      const b = data[si];
      const sx = x(si), sy = y(b.c);
      // vertical crosshair
      ctx.beginPath();
      ctx.moveTo(sx, padT - 4);
      ctx.lineTo(sx, padT + ih);
      ctx.strokeStyle = "rgba(255,255,255,0.35)";
      ctx.lineWidth = 1;
      ctx.stroke();
      // dot
      ctx.beginPath();
      ctx.arc(sx, sy, 4.5, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.beginPath();
      ctx.arc(sx, sy, 4.5, 0, Math.PI * 2);
      ctx.strokeStyle = "#000";
      ctx.lineWidth = 2;
      ctx.stroke();
      // floating price pill
      const label = (fmtRef.current ?? ((v: number) => v.toFixed(2)))(b.c);
      ctx.font = "600 12px -apple-system, BlinkMacSystemFont, sans-serif";
      const tw = ctx.measureText(label).width;
      const pw = tw + 16, ph = 24;
      let px = sx - pw / 2;
      px = Math.max(4, Math.min(W - pw - 4, px));
      const py = Math.max(2, sy - ph - 10);
      ctx.fillStyle = "rgba(28,28,30,0.94)";
      ctx.beginPath();
      (ctx as any).roundRect?.(px, py, pw, ph, 7) ?? ctx.rect(px, py, pw, ph);
      ctx.fill();
      ctx.fillStyle = "#fff";
      ctx.textBaseline = "middle";
      ctx.fillText(label, px + 8, py + ph / 2 + 0.5);
      // date under finger
      const dt = new Date(b.t);
      const dLabel = dt.toLocaleDateString("en-US", { month: "short", day: "numeric" }) +
        (data.length > 100 ? ` '${String(dt.getFullYear()).slice(2)}` : "") +
        (stepIsIntraday(data) ? ` ${dt.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}` : "");
      ctx.font = "500 11px -apple-system, BlinkMacSystemFont, sans-serif";
      ctx.fillStyle = "rgba(255,255,255,0.55)";
      const dw = ctx.measureText(dLabel).width;
      ctx.fillText(dLabel, Math.max(4, Math.min(W - dw - 4, sx - dw / 2)), padT + ih + 2);
    } else {
      // live end dot
      const lx = x(data.length - 1), ly = y(data[data.length - 1].c);
      ctx.beginPath();
      ctx.arc(lx - 1, ly, 3.5, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
    }
  };

  const stepIsIntraday = (data: CBar[]) =>
    data.length > 1 && data[1].t - data[0].t < 12 * 3600e3;

  const scheduleDraw = () => {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(draw);
  };

  useEffect(() => {
    const wrap = wrapRef.current, canvas = canvasRef.current;
    if (!wrap || !canvas) return;

    const idxFromEvent = (clientX: number) => {
      const rect = canvas.getBoundingClientRect();
      const data = barsRef.current;
      const fx = (clientX - rect.left - 4) / (rect.width - 12);
      return Math.max(0, Math.min(data.length - 1, Math.round(fx * (data.length - 1))));
    };

    const onDown = (e: PointerEvent) => {
      scrubRef.current = idxFromEvent(e.clientX);
      cbRef.current?.(barsRef.current[scrubRef.current]);
      scheduleDraw();
    };
    const onMove = (e: PointerEvent) => {
      // mouse: hover scrubs; touch/pen: scrub only while touching
      if (e.pointerType !== "mouse" && scrubRef.current == null) return;
      const i = idxFromEvent(e.clientX);
      if (i !== scrubRef.current) {
        scrubRef.current = i;
        cbRef.current?.(barsRef.current[i]);
        scheduleDraw();
      }
    };
    const onUp = () => {
      if (scrubRef.current != null) {
        scrubRef.current = null;
        cbRef.current?.(null);
        scheduleDraw();
      }
    };

    canvas.addEventListener("pointerdown", onDown);
    canvas.addEventListener("pointermove", onMove, { passive: true });
    canvas.addEventListener("pointerup", onUp);
    canvas.addEventListener("pointercancel", onUp);
    canvas.addEventListener("pointerleave", onUp);

    const ro = new ResizeObserver(scheduleDraw);
    ro.observe(wrap);
    scheduleDraw();
    return () => {
      cancelAnimationFrame(rafRef.current);
      ro.disconnect();
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerup", onUp);
      canvas.removeEventListener("pointercancel", onUp);
      canvas.removeEventListener("pointerleave", onUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    scrubRef.current = null;
    scheduleDraw();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bars]);

  return (
    <div ref={wrapRef} style={{ width: "100%", touchAction: "pan-y", cursor: "crosshair" }}>
      <canvas ref={canvasRef} style={{ display: "block", width: "100%", height }} />
    </div>
  );
}
