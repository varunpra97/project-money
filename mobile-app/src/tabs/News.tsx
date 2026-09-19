import { useState } from "react";
import { useResource } from "../lib/resource";
interface Article { id: string; title: string; url: string; source: string; category: string; published: string|null; stale: boolean; }
interface Idea { id: string; title: string; detail: string; measure: string; effort: string; related_title: string|null; related_url: string|null; }
interface Feed { checked_at: string; items: Article[]; ideas: Idea[]; sources: {name: string; fetched: string|null; stale: boolean}[]; }
export default function News() {
  const [filter,setFilter] = useState("All");
  const {data,loading,error,refresh} = useResource<Feed>("/api/news",600000);
  const items = data?.items.filter(x=>filter === "All" || x.category === filter) ?? [];
  return <div className="insight-page">
    <header className="page-heading"><div><div className="eyebrow">THE BIGGER PICTURE</div><h1>News & ideas</h1></div><button className="subtle-button" onClick={refresh}>Refresh</button></header>
    <p className="page-description">Market context, options updates, and ways to make Pulse better.</p>
    <div className="segment" role="group" aria-label="Feed category">{["All","Options","Markets","Product lab"].map(f=><button key={f} aria-pressed={f===filter} className={f===filter?"selected":""} onClick={()=>setFilter(f)}>{f}</button>)}</div>
    {error && <div className="notice" role="alert">{error} <button onClick={refresh}>Retry</button></div>}
    {loading && !data && <div className="sk" style={{height:280}}/>}
    {data && <>
      <div className="source-status">Checked {new Date(data.checked_at).toLocaleString()} · refreshes every 10 min</div>
      {data.sources.some(s=>s.stale) && <div className="notice">Some sources are unavailable. Previously fetched headlines are labeled cached; no substitute headlines are generated.</div>}
      {filter!=="Product lab" && <div className="news-list">{items.length ? items.map((a,i)=><article className={`news-card ${i===0?"lead-story":""}`} key={a.id}><div className="article-meta"><span>{a.category}</span><span>{a.source}{a.stale?" · cached":""}</span></div><a href={a.url} target="_blank" rel="noopener noreferrer"><h2>{a.title} <span aria-hidden="true">↗</span></h2></a><time dateTime={a.published??undefined}>{a.published ? new Date(a.published).toLocaleString() : "Publication date unavailable"}</time></article>):<div className="empty">No headlines are available in this category. Try again shortly.</div>}</div>}
      {(filter==="All" || filter==="Product lab") && <section className="product-lab"><div className="eyebrow">PRODUCT LAB · EDITORIAL SUGGESTIONS</div><h2>Build a better feedback loop</h2><p className="page-description">Ideas for improving this product, not news reports or trading recommendations.</p>{data.ideas.map((idea,i)=><article className="idea-card" key={idea.id}><div className="article-meta"><span>0{i+1} / PRODUCT IDEA</span><span>{idea.effort} effort</span></div><h3>{idea.title}</h3><p>{idea.detail}</p><div className="measure"><strong>How to evaluate it</strong><p>{idea.measure}</p></div>{idea.related_url && <a className="related-link" href={idea.related_url} target="_blank" rel="noopener noreferrer">Related headline: {idea.related_title} ↗</a>}</article>)}</section>}
      <details className="data-notes"><summary>Sources & freshness</summary>{data.sources.map(s=><p key={s.name}>{s.name} · {s.fetched?new Date(s.fetched).toLocaleString():"Not yet fetched"}{s.stale?" · unavailable / cached":""}</p>)}<p>Headlines link to their publishers. Publication times are supplied by each source. Product ideas use curated themes matched to headlines.</p></details>
    </>}
  </div>;
}
