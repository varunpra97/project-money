import { useEffect, useState } from 'react';
type Config={id?:string;name:string;symbols:string[];start:string;end:string;interval:string;rule:string};
type Result={matches:{symbol:string;date:string;close:number;indicator:number}[];total_matches:number;truncated:boolean;errors:{symbol:string;error:string}[];warnings:string[];note:string};
type Job={id:string;state:string;result:Result|null;error:string|null};
const rules=[['sma20_cross_up','Cross above SMA 20'],['above_sma200','Close above SMA 200'],['rsi14_oversold','RSI 14 below 30'],['rsi14_overbought','RSI 14 above 70'],['breakout20','Break above prior 20-bar high']];
const day=(d:Date)=>d.toISOString().slice(0,10);
export default function Historical(){
 const [name,setName]=useState('My scanner'),[symbols,setSymbols]=useState('AAPL, MSFT, SPY');
 const [start,setStart]=useState(day(new Date(Date.now()-90*86400000))),[end,setEnd]=useState(day(new Date()));
 const [interval,setIntervalValue]=useState('1d'),[rule,setRule]=useState('sma20_cross_up');
 const [saved,setSaved]=useState<Config[]>([]),[job,setJob]=useState<Job|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[note,setNote]=useState('');
 async function api(path:string,body?:unknown){const base=location.pathname.startsWith('/pulse')?'/pulse':'';const r=await fetch(base+'/api/history'+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json','X-Pulse-Scanner':'1'},body:body?JSON.stringify(body):undefined,cache:'no-store'});const j=await r.json();if(!r.ok)throw new Error(typeof j.detail==='string'?j.detail:'Check the dates and ticker symbols (maximum 20).');return j;}
 const config=()=>({name,symbols:symbols.split(/[\s,]+/).filter(Boolean).map(x=>x.toUpperCase()),start,end,interval,rule});
 useEffect(()=>{api('/scanners').then(setSaved).catch(e=>setError(e.message));},[]);
 useEffect(()=>{if(!job||job.state!=='running')return;let active=true;const timer=setInterval(()=>api('/jobs/'+job.id).then(j=>{if(active)setJob(j)}).catch(e=>{if(active)setError(e.message)}),1000);return()=>{active=false;clearInterval(timer)};},[job?.id,job?.state]);
 async function action(kind:'run'|'save'){setBusy(true);setError('');setNote('');try{if(kind==='run')setJob(await api('/run',config()));else{await api('/scanners',config());setSaved(await api('/scanners'));setNote('Scanner saved on the backend.');}}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 function load(c:Config){setName(c.name);setSymbols(c.symbols.join(', '));setStart(c.start);setEnd(c.end);setIntervalValue(c.interval);setRule(c.rule);setJob(null);}
 return <div className="historical"><div className="screen-title">Historical scanners</div><p className="caption">Find technical signals in past stock data. Rules use data available at each bar; these are not strategy backtests.</p>
 {saved.length>0&&<label>Saved scanners<select defaultValue="" onChange={e=>{const c=saved.find(x=>x.id===e.target.value);if(c)load(c)}}><option value="">Choose a scanner</option>{saved.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>}
 <form onSubmit={e=>{e.preventDefault();action('run')}}>
 <label>Name<input value={name} onChange={e=>setName(e.target.value)} required maxLength={80}/></label>
 <label>Tickers (up to 20)<input value={symbols} onChange={e=>setSymbols(e.target.value)} required placeholder="AAPL, MSFT, SPY"/></label>
 <div className="stat-grid"><label>From<input type="date" value={start} max={end} onChange={e=>setStart(e.target.value)} required/></label><label>Through<input type="date" value={end} min={start} max={day(new Date())} onChange={e=>setEnd(e.target.value)} required/></label></div>
 <label>Timeframe<select value={interval} onChange={e=>setIntervalValue(e.target.value)}><option value="1d">Daily</option><option value="1wk">Weekly</option><option value="1mo">Monthly</option></select></label>
 <label>Rule<select value={rule} onChange={e=>setRule(e.target.value)}>{rules.map(([v,t])=><option key={v} value={v}>{t}</option>)}</select></label>
 <div className="chart-toolbar"><button type="submit" disabled={busy||job?.state==='running'}>Run historical scan</button><button type="button" disabled={busy} onClick={()=>action('save')}>Save configuration</button></div></form>
 {note&&<p className="caption">{note}</p>}{error&&<div className="notice" role="alert">{error}</div>}
 {job?.state==='running'&&<div className="notice" role="status">Scanning historical bars… You can keep using other tabs.</div>}
 {job?.error&&<div className="notice">{job.error}</div>}
 {job?.result&&<><h3>{job.result.total_matches} matches</h3><p className="caption">{job.result.note}</p>{job.result.warnings.map(w=><p className="caption" key={w}>{w}</p>)}{job.result.errors.map(e=><div className="notice" key={e.symbol}>{e.symbol}: {e.error}</div>)}<div style={{overflowX:'auto'}}><table><thead><tr><th>Date</th><th>Ticker</th><th>Close</th><th>Indicator</th></tr></thead><tbody>{job.result.matches.slice(0,200).map((m,i)=><tr key={i}><td>{m.date}</td><td>{m.symbol}</td><td>{m.close.toFixed(2)}</td><td>{m.indicator.toFixed(2)}</td></tr>)}</tbody></table></div>{job.result.total_matches>200&&<p className="caption">Showing the latest 200 matches. Narrow the dates for a smaller result set.</p>}</>}
 </div>;
}
