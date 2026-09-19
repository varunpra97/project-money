import { useEffect, useState } from 'react';
type Tick={symbol:string;price:number|null;state:string;as_of?:string;source:string;timestamp?:number};
export default function LivePrice({symbol}:{symbol:string}) {
  const [quote,setQuote]=useState<Tick|null>(null);
  const [connected,setConnected]=useState(false);
  const [delivery,setDelivery]=useState<number|null>(null);
  const [now,setNow]=useState(Date.now());
  useEffect(()=>{
    setQuote(null);setConnected(false);
    const base=location.pathname.startsWith('/pulse')?'/pulse':'';
    const source=new EventSource(`${base}/api/live/events?symbols=${encodeURIComponent(symbol)}`);
    source.onopen=()=>setConnected(true);
    source.onerror=()=>setConnected(false);
    source.onmessage=e=>{try{const r=JSON.parse(e.data);setQuote(r.quotes[0]??null);setDelivery(Math.max(0,Date.now()-r.sent_at*1000));setConnected(true);}catch{setConnected(false);}};
    const timer=setInterval(()=>setNow(Date.now()),1000);
    return()=>{source.close();clearInterval(timer);};
  },[symbol]);
  const age=quote?.timestamp?Math.max(0,(now-quote.timestamp*1000)/1000):null;
  const state=!connected?'Reconnecting':age!=null&&age>90?'Last available':quote?.state==='stream'?'Streaming':quote?.state==='polling'?'Polling fallback':'Connecting';
  return <section className="live-quote" aria-label={`${symbol} latest stock price`}>
    <div><span className={connected&&quote?.state==='stream'&&age!=null&&age<=90?'up':'muted'}>● {state}</span> · <strong>{symbol} {quote?.price!=null?quote.price.toLocaleString(undefined,{style:'currency',currency:'USD'}):'—'}</strong></div>
    <small>{quote?.as_of?`Source: ${new Date(quote.as_of).toLocaleString()} · ${Math.floor(age??0)}s old`:'Waiting for source data. Chart history remains available.'}</small>
    <details><summary>Latency & improvements</summary><p>Push delivery: {delivery==null?'measuring':`${Math.round(delivery)} ms`} (approximate; device clocks affect this). Stock updates stream when available; fallback checks every 20 seconds. Historical candles refresh every 20 seconds. Greeks and saved paper marks update separately.</p><p>Next: measure Windows-to-phone p50/p95, keep server/device clocks synchronized, locate the server closer to the data source, and add a licensed exchange feed. Provider timestamps can lag; “streaming” does not guarantee exchange-real-time pricing.</p></details>
  </section>;
}
