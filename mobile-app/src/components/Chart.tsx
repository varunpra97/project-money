import { useEffect, useMemo, useRef, useState } from "react";
export interface CBar { t:number; c:number; o?:number; h?:number; l?:number; v?:number }
interface Props { bars:CBar[]; height?:number; lineWidth?:number; onScrub?:(bar:CBar|null)=>void; fmtPrice?:(v:number)=>string }
import { indicators } from "../lib/indicators";
export default function Chart({bars,height=280,onScrub,fmtPrice=(v)=>v.toFixed(2)}:Props) {
  const [mode,setMode]=useState("candles");
  const [study,setStudy]=useState("sma");
  const [volume,setVolume]=useState(true);
  const [count,setCount]=useState(100);
  const [offset,setOffset]=useState(0);
  const [selected,setSelected]=useState<number|null>(null);
  const [expanded,setExpanded]=useState(false);
  const host=useRef<HTMLDivElement>(null);
  const values=useMemo(()=>indicators(bars),[bars]);
  useEffect(()=>{setOffset(0);setSelected(null);onScrub?.(null);},[bars]);
  const end=Math.max(1,bars.length-offset),start=Math.max(0,end-count);
  const data=bars.slice(start,end),studies=values.slice(start,end);
  const W=800,H=expanded?480:Math.max(280,height),left=8,right=72,top=18,bottom=28;
  const priceBottom=H-bottom-(volume?65:0);
  const hasOHLC=data.every(b=>[b.o,b.h,b.l].every(v=>v!=null&&Number.isFinite(v)));
  const studyVals=studies.flatMap(s=>study==='sma'?[s.sma]:study==='ema'?[s.ema]:study==='bb'?[s.upper,s.lower]:[]).filter((v):v is number=>v!=null);
  const lows=data.map(b=>hasOHLC?b.l!:b.c),highs=data.map(b=>hasOHLC?b.h!:b.c);
  const low=Math.min(...lows,...studyVals),high=Math.max(...highs,...studyVals),pad=Math.max((high-low)*.08,Math.abs(high)*.001,.01);
  const min=low-pad,max=high+pad;
  const x=(i:number)=>left+(i+.5)*(W-left-right)/Math.max(1,data.length);
  const y=(v:number)=>top+(max-v)/(max-min)*(priceBottom-top);
  const path=(get:(i:number)=>number|null)=>data.map((_,i)=>{const v=get(i);return v==null?'':`${i===0||get(i-1)==null?'M':'L'}${x(i)},${y(v)}`;}).join(' ');
  const selectedBar=selected==null?data[data.length-1]:data[selected];
  const selectedStudy=studies[selected??(data.length-1)];
  const barWidth=Math.max(1,(W-left-right)/Math.max(data.length,1)*.65);
  const volMax=Math.max(1,...data.map(b=>b.v??0));
  const date=(t:number)=>new Date(t*1000).toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
  function inspect(e:React.PointerEvent<SVGSVGElement>){const r=e.currentTarget.getBoundingClientRect();const i=Math.max(0,Math.min(data.length-1,Math.floor(((e.clientX-r.left)/r.width*W-left)/(W-left-right)*data.length)));setSelected(i);onScrub?.(data[i]);}
  if(!data.length)return <div className="empty">No chart data available.</div>;
  return <div ref={host} className={`trading-chart ${expanded?'chart-expanded':''}`}>
    <div className="chart-toolbar">
      <select aria-label="Chart type" value={mode} onChange={e=>setMode(e.target.value)}><option value="candles">Candlesticks</option><option value="line">Line</option></select>
      <select aria-label="Technical indicator" value={study} onChange={e=>setStudy(e.target.value)}><option value="none">No indicator</option><option value="sma">SMA 20</option><option value="ema">EMA 20</option><option value="bb">Bollinger 20 · 2σ</option></select>
      <label><input type="checkbox" checked={volume} onChange={e=>setVolume(e.target.checked)}/> Volume</label>
      <button onClick={()=>setExpanded(v=>!v)}>{expanded?'Close expanded chart':'Expand'}</button>
    </div>
    <div className="chart-readout">{selectedBar&&<>{date(selectedBar.t)} · {hasOHLC?`O ${fmtPrice(selectedBar.o!)} H ${fmtPrice(selectedBar.h!)} L ${fmtPrice(selectedBar.l!)} `:''}C {fmtPrice(selectedBar.c)} · Vol {(selectedBar.v??0).toLocaleString()}</>}</div>
    {mode==='candles'&&!hasOHLC&&<div className="caption">OHLC unavailable; showing close-price line. Refresh to retrieve candles.</div>}
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${mode} price chart with ${study} indicator`} style={{width:'100%',display:'block',touchAction:'pan-y'}} onPointerMove={inspect} onPointerDown={inspect} onPointerLeave={()=>{setSelected(null);onScrub?.(null);}}>
      {[0,1,2,3,4].map(i=>{const v=min+(max-min)*i/4;return <g key={i}><line x1={left} x2={W-right} y1={y(v)} y2={y(v)} stroke="#292d34"/><text x={W-right+8} y={y(v)+4} fill="#9ca3af" fontSize="12">{fmtPrice(v)}</text></g>;})}
      {mode==='candles'&&hasOHLC?data.map((b,i)=>{const color=b.c>=b.o!?'#26c6a2':'#ef5350';return <g key={b.t} stroke={color} fill={color}><line x1={x(i)} x2={x(i)} y1={y(b.h!)} y2={y(b.l!)}/><rect x={x(i)-barWidth/2} width={barWidth} y={Math.min(y(b.o!),y(b.c))} height={Math.max(1,Math.abs(y(b.o!)-y(b.c)))}/></g>;}):<path d={path(i=>data[i].c)} fill="none" stroke="#26c6a2" strokeWidth="2"/>}
      {(study==='sma'||study==='ema')&&<path d={path(i=>studies[i][study])} fill="none" stroke={study==='sma'?'#ffbc57':'#68aaff'} strokeWidth="2"/>}
      {study==='bb'&&(['upper','sma','lower'] as const).map(k=><path key={k} d={path(i=>studies[i][k])} fill="none" stroke={k==='sma'?'#ffbc57':'#a394ff'} strokeWidth="1.5" strokeDasharray={k==='sma'?'4 3':undefined}/>)}
      {volume&&data.map((b,i)=><rect key={b.t} x={x(i)-barWidth/2} width={barWidth} y={H-bottom-55*(b.v??0)/volMax} height={55*(b.v??0)/volMax} fill={b.c>=(b.o??b.c)?'#26c6a260':'#ef535060'}/>)}
      {selected!=null&&data[selected]&&<g stroke="#b6bcc8" strokeDasharray="4 4"><line x1={x(selected)} x2={x(selected)} y1={top} y2={H-bottom}/><line x1={left} x2={W-right} y1={y(data[selected].c)} y2={y(data[selected].c)}/></g>}
      {[0,Math.floor((data.length-1)/2),data.length-1].map((i,n)=><text key={n} x={x(i)} y={H-6} textAnchor={n===0?'start':n===2?'end':'middle'} fontSize="11" fill="#9ca3af">{new Date(data[i].t*1000).toLocaleDateString(undefined,{month:'short',day:'numeric'})}</text>)}
    </svg>
    <div className="chart-toolbar"><button aria-label="Pan earlier" disabled={end<=count} onClick={()=>{setOffset(Math.min(bars.length-count,offset+Math.ceil(count/3)));setSelected(null);}}>← Earlier</button><button disabled={!offset} onClick={()=>{setOffset(Math.max(0,offset-Math.ceil(count/3)));setSelected(null);}}>Later →</button><button aria-label="Zoom in" disabled={count<=20} onClick={()=>{setCount(Math.max(20,Math.floor(count/1.5)));setSelected(null);}}>＋</button><button aria-label="Zoom out" disabled={count>=bars.length} onClick={()=>{setCount(Math.min(bars.length,Math.ceil(count*1.5)));setOffset(0);setSelected(null);}}>−</button><button onClick={()=>{setCount(bars.length);setOffset(0);setSelected(null);}}>Fit</button></div>
    <div className="caption">{study!=='none'&&(selectedStudy?.sma==null?'Indicators need 20 bars. ':`${study.toUpperCase()} 20: ${fmtPrice(study==='ema'?selectedStudy.ema!:selectedStudy.sma!)} · `)}Indicators use the displayed interval. Yahoo Finance data may be delayed.</div>
  </div>;
}
