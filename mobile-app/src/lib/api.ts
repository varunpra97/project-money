import { useEffect, useRef, useState } from "react";
import { company } from "./demo";
export interface ApiState<T> { data:T|null; loading:boolean; demo:boolean; stale:boolean; error:string|null; refresh:()=>void; }
const memory = new Map<string, any>();
export function useApi<T>(path:string|null, opts?:{timeoutMs?:number}):ApiState<T> {
  const [version,setVersion]=useState(0);
  const [state,setState]=useState<{data:T|null;loading:boolean;stale:boolean;error:string|null}>({data:null,loading:!!path,stale:false,error:null});
  const current=useRef(path);current.current=path;
  useEffect(()=>{
    if(!path){setState({data:null,loading:false,stale:false,error:null});return;}
    let active=true;
    let controller=new AbortController();
    let inflight=false;
    const initial=memory.get(path)||null;
    setState({data:initial,loading:!initial,stale:!!initial,error:null});
    async function load(force=false){
      if(inflight)return;
      inflight=true;controller=new AbortController();
      const timeout=setTimeout(()=>controller.abort(),opts?.timeoutMs??35000);
      try{
        const base=location.pathname.startsWith("/pulse")?"/pulse":"";
        const url=base+path+(force?(path!.includes("?")?"&":"?")+"refresh=true":"");
        const res=await fetch(url,{signal:controller.signal,cache:"no-store"});
        const data=await res.json();
        if(!res.ok||data.error)throw new Error(data.error||data.detail||"The provider is temporarily unavailable.");
        if(active&&current.current===path){memory.set(path!,data);setState({data,loading:false,stale:false,error:null});}
      }catch(e){if(active){const error=e instanceof Error?e.message:"Unable to fetch data";setState({data:memory.get(path!)||null,loading:false,stale:memory.has(path!),error});}}
      finally{clearTimeout(timeout);inflight=false;}
    }
    load(version>0);
    const poll=setInterval(()=>{if(document.visibilityState=== "visible")load();},path.includes("/quote/")?20000:60000);
    const onFocus=()=>load();window.addEventListener("focus",onFocus);
    return()=>{active=false;clearInterval(poll);controller.abort();window.removeEventListener("focus",onFocus);};
  },[path,version,opts?.timeoutMs]);
  return {...state,demo:false,refresh:()=>setVersion(v=>v+1)};
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
