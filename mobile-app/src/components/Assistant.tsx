import { useEffect, useRef, useState } from "react";

type Message = {id:string; role:string; text:string};
type Approval = {id:string; kind:string; detail:string; reason?:string; cwd?:string};
type Chat = {id:string; title:string; messages:Message[]; busy:boolean; error:string|null; activity:string; diff:string; approvals:Approval[]; changes:unknown[]};
type Status = {ready:boolean; message:string; provider:string; context:string[]};
const base = () => location.pathname.startsWith("/pulse") ? "/pulse" : "";
function stored(key:string) { try{return localStorage.getItem(key)||"";}catch{return "";} }
function save(key:string,value:string) { try{localStorage.setItem(key,value);}catch{} }

export default function Assistant({screen, onClose, standalone=false}:{screen:string;onClose?:()=>void;standalone?:boolean}) {
  const [token,setToken]=useState(()=>stored("pulse-assistant-token"));
  const [pairCode,setPairCode]=useState("");
  const [displayCode,setDisplayCode]=useState("");
  const [status,setStatus]=useState<Status|null>(null);
  const [chat,setChat]=useState<Chat|null>(null);
  const [chatID,setChatID]=useState(()=>stored("pulse-assistant-chat"));
  const [chats,setChats]=useState<{id:string;title:string;busy:boolean}[]>([]);
  const [text,setText]=useState("");
  const [mode,setMode]=useState("ask");
  const [error,setError]=useState("");
  const [sending,setSending]=useState(false);
  const [checking,setChecking]=useState(false);
  const bottom=useRef<HTMLDivElement>(null);
  async function api(path:string, body?:unknown, auth=token) {
    const response=await fetch(base()+"/api/assistant"+path,{method:body===undefined?"GET":"POST",headers:{"X-Pulse-Assistant":"1","Content-Type":"application/json",...(auth?{Authorization:`Bearer ${auth}`}:{})},body:body===undefined?undefined:JSON.stringify(body),cache:"no-store"});
    const result=await response.json();
    if(!response.ok) {if(response.status===401){setToken("");save("pulse-assistant-token","");}throw new Error(typeof result.detail === "string"?result.detail:"Assistant request failed.");}
    return result;
  }
  async function connect() {
    setChecking(true);setError("");
    try {
      let key=token;
      if(location.hostname==="localhost" || location.hostname==="127.0.0.1") {
        const bootstrap=await api("/bootstrap",undefined,"");key=bootstrap.token;setToken(key);save("pulse-assistant-token",key);setDisplayCode(bootstrap.pairing_code);
      }
      if(key) {setStatus(await api("/status",undefined,key));setChats(await api("/chats",undefined,key));}
    }catch(e){setError(String(e instanceof Error?e.message:e));}finally{setChecking(false);}
  }
  useEffect(()=>{connect();},[]);
  useEffect(()=>{
    if(!token||!chatID)return;
    let active=true;
    async function poll(){try{const c=await api(`/chats/${chatID}`);if(active)setChat(c);}catch(e){if(active)setError(String(e instanceof Error?e.message:e));}}
    poll(); const timer=setInterval(poll,1000);
    return()=>{active=false;clearInterval(timer);};
  },[token,chatID]);
  useEffect(()=>{bottom.current?.scrollIntoView({block:"nearest"});},[chat?.messages.map(x=>x.text).join(""),chat?.activity]);
  function select(id:string){setChat(null);setChatID(id);save("pulse-assistant-chat",id);setError("");}
  async function send(value=text){
    if(!value.trim()||sending||chat?.busy)return;
    setSending(true);setError("");
    try{const c=await api("/messages",{text:value,chat_id:chatID||null,mode,screen});setChat(c);setChatID(c.id);save("pulse-assistant-chat",c.id);setText("");setChats(await api("/chats"));}
    catch(e){setError(String(e instanceof Error?e.message:e));}finally{setSending(false);}
  }
  async function act(path:string,body:unknown){try{await api(path,body);}catch(e){setError(String(e instanceof Error?e.message:e));}}
  async function pair(){setError("");try{const r=await api("/pair",{code:pairCode},"");setToken(r.token);save("pulse-assistant-token",r.token);setStatus(await api("/status",undefined,r.token));setChats(await api("/chats",undefined,r.token));}catch(e){setError(String(e instanceof Error?e.message:e));}}
  return <aside className={`assistant-panel ${standalone?"standalone":""}`} aria-label="Pulse assistant">
    <header className="assistant-heading"><div className="assistant-avatar">✦</div><div><strong>Pulse Assistant</strong><small>Powered by Codex</small></div><button aria-label="New conversation" title="New conversation" onClick={()=>select("")}>＋</button>{onClose&&<button aria-label="Close assistant" onClick={onClose}>×</button>}</header>
    <div className="assistant-context"><span className={status?.ready?"connected-dot":"offline-dot"}/>{status?.ready?"Connected":"Connection needed"}<span>Viewing {screen}</span></div>
    {chats.length>0&&<select aria-label="Conversation" className="conversation-select" value={chatID} onChange={e=>select(e.target.value)}><option value="">New conversation</option>{chats.map(c=><option key={c.id} value={c.id}>{c.busy?"● ":""}{c.title}</option>)}</select>}
    <div className="assistant-messages" role="log" aria-label="Conversation messages" aria-live="polite">
      {!token&&<section className="assistant-setup"><h3>Connect to your Mac</h3><p>Open the assistant at localhost:8505 on your Mac and copy its pairing code below. This connects this device to your source code and conversations.</p><input aria-label="Pairing code" inputMode="numeric" maxLength={8} value={pairCode} onChange={e=>setPairCode(e.target.value.replace(/\D/g,""))} placeholder="8-digit pairing code"/><button disabled={pairCode.length!==8} onClick={pair}>Pair device</button></section>}
      {token&&!status?.ready&&<section className="assistant-setup"><h3>Your coding companion</h3><p>{checking?"Connecting to local Codex…":status?.message||"Checking your connection…"}</p><p>Uses the Codex account signed in on your Mac. If setup is needed, run <code>bash setup-pulse-assistant.sh</code> there.</p><button onClick={connect} disabled={checking}>Check connection</button></section>}
      {!chat?.messages.length&&status?.ready&&<div className="assistant-welcome"><h2>What would you like to work on?</h2><p>I can explain your portfolio, inspect Pulse’s code, or help change the app.</p>{["Explain my current paper P&L and missing history.","Why might this screen show missing data?","Suggest the next improvement to Pulse."].map(t=><button key={t} onClick={()=>send(t)} disabled={sending}>{t} ↗</button>)}</div>}
      {chat?.messages.map(m=><div className={`chat-message ${m.role}`} key={m.id}><div className="message-role">{m.role==="user"?"You":"Pulse Assistant"}</div><div className="message-text">{m.text||"…"}</div></div>)}
      {chat?.busy&&<div className="assistant-working"><span className="working-spinner"/>{chat.activity||"Working…"}</div>}
      {(error||chat?.error)&&<div className="notice" role="alert">{error||chat?.error}</div>}
      {!!chat?.diff&&<details className="assistant-diff"><summary>Source changes</summary><pre>{chat.diff}</pre></details>}
      {chat?.approvals.map(a=><section className="assistant-approval" key={a.id}><strong>Permission requested</strong><pre>{a.detail}</pre>{a.reason&&<p>{a.reason}</p>}{a.cwd&&<small>{a.cwd}</small>}<div><button onClick={()=>act(`/chats/${chat.id}/approvals/${a.id}`,{approve:true})}>Approve once</button><button onClick={()=>act(`/chats/${chat.id}/approvals/${a.id}`,{approve:false})}>Decline</button></div></section>)}
      <div ref={bottom}/>
    </div>
    <footer className="assistant-composer"><div className="composer-controls"><select aria-label="Assistant mode" value={mode} disabled={sending||chat?.busy} onChange={e=>setMode(e.target.value)}><option value="ask">Ask · read only</option><option value="edit">Edit app · repository access</option></select>{chat?.busy&&<button onClick={()=>act(`/chats/${chat.id}/stop`,{})}>Stop</button>}</div><textarea aria-label="Message assistant" placeholder={mode==="ask"?"Ask about the app or portfolio…":"Describe the change to make…"} value={text} onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send();}}}/><button className="assistant-send" disabled={!status?.ready||!text.trim()||sending||chat?.busy} onClick={()=>send()}>{sending?"Starting…":"Send ↑"}</button><small>{mode==="edit"?"May edit, test, commit, rebase and push this repository. iOS changes still need a rebuild.":"Context: this screen, paper portfolio, news and project source. Messages are sent to OpenAI."}</small><details className="pairing-details" onToggle={e=>{if(e.currentTarget.open)connect();}}><summary>Connection & device pairing</summary>{displayCode?<p>Pairing code: <strong>{displayCode}</strong><br/>Valid for 10 minutes. Enter it only on your own device.</p>:<p>Pairing codes are shown in the assistant on localhost on your Mac.</p>}</details></footer>
  </aside>;
}
