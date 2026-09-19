import { Component, Suspense, lazy, useState, type ReactNode } from "react";

import Assistant from "./components/Assistant";

const Home = lazy(() => import("./tabs/Home"));
const Discover = lazy(() => import("./tabs/Discover"));
const Search = lazy(() => import("./tabs/Search"));
const Activity = lazy(() => import("./tabs/Activity"));

const Performance = lazy(() => import("./tabs/Performance"));
const Historical = lazy(() => import("./tabs/Historical"));
const News = lazy(() => import("./tabs/News"));
const TABS_UNSORTED = [
  { key: "historical", label: "Scanners", icon: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 4v16h16M7 15l4-5 4 2 5-6"/></svg> },
  { key: "performance", label: "Stats", icon: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 20V10m8 10V4m8 16V8"/></svg> },
  { key: "news", label: "News", icon: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="4" width="18" height="17" rx="2"/><path d="M7 8h10M7 12h10M7 16h6"/></svg> },
  {
    key: "home", label: "Home",
    icon: (a: boolean) => (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={a ? 2.4 : 1.8} strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 10.5 12 3l9 7.5" /><path d="M5 9.5V21h14V9.5" />
      </svg>
    ),
  },
  {
    key: "discover", label: "Discover",
    icon: (a: boolean) => (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={a ? 2.4 : 1.8} strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="9" /><path d="M12 3v3M12 18v3M3 12h3M18 12h3" />
      </svg>
    ),
  },
  {
    key: "search", label: "Search",
    icon: (a: boolean) => (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={a ? 2.4 : 1.8} strokeLinecap="round">
        <circle cx="11" cy="11" r="7" /><path d="m20 20-3.8-3.8" />
      </svg>
    ),
  },
  {
    key: "activity", label: "Activity",
    icon: (a: boolean) => (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={a ? 2.4 : 1.8} strokeLinecap="round" strokeLinejoin="round">
        <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8z" />
      </svg>
    ),
  },
] as const;

const ORDER = ["home", "performance", "news", "discover", "search", "historical", "activity"];
const TABS = [...TABS_UNSORTED].sort((a,b) => ORDER.indexOf(a.key)-ORDER.indexOf(b.key));
type TabKey = (typeof TABS)[number]["key"];

function TabSkeleton() {
  return (
    <div>
      <div className="sk" style={{ height: 34, width: "45%", marginBottom: 14 }} />
      <div className="sk" style={{ height: 220, marginBottom: 12 }} />
      <div className="sk" style={{ height: 76, marginBottom: 10 }} />
      <div className="sk" style={{ height: 76 }} />
    </div>
  );
}

/** Last line of defense: a render crash can never blank the whole app again. */
class TabErrorBoundary extends Component<{ children: ReactNode; tab: string }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { /* swallowed: fallback UI below */ }
  render() {
    if (this.state.failed) {
      return (
        <div>
          <div className="screen-title">Something glitched</div>
          <div className="empty" style={{ marginTop: 12 }}>
            This tab hit a rendering error. Your data is safe — try reloading it.
          </div>
          <button
            type="button"
            className="retry-btn"
            style={{ marginTop: 12 }}
            onClick={() => this.setState({ failed: false })}
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  const [tab, setTab] = useState<TabKey>("home");

  const [assistantOpen, setAssistantOpen] = useState(false);
  const params = new URLSearchParams(location.search);
  if (params.get("assistant") === "1") return <Assistant standalone screen={params.get("screen") || "iOS app"}/>;
  return (
    <div className={`app ${assistantOpen ? "with-assistant" : ""}`}>
      <button type="button" className="assistant-launch" onClick={()=>setAssistantOpen(v=>!v)} aria-expanded={assistantOpen}>✦ Assistant</button>
      {assistantOpen && <Assistant screen={tab} onClose={()=>setAssistantOpen(false)}/>}
      <main className="main" key={tab}>
        <TabErrorBoundary tab={tab} key={tab}>
          <Suspense fallback={<TabSkeleton />}>
            {tab === "home" && <Home />}
            {tab === "performance" && <Performance />}
            {tab === "news" && <News />}
            {tab === "historical" && <Historical />}
            {tab === "discover" && <Discover />}
            {tab === "search" && <Search />}
            {tab === "activity" && <Activity />}
          </Suspense>
        </TabErrorBoundary>
      </main>
      <nav className="tabbar" aria-label="Primary">
        <div className="tabbar-inner">
          {TABS.map((t) => (
            <button
              type="button"
              key={t.key}
              className={`tab${tab === t.key ? " active" : ""}`}
              aria-current={tab === t.key ? "page" : undefined}
              onClick={() => {
                setTab(t.key);
                // keep scroll at top when switching tabs
                window.scrollTo({ top: 0 });
              }}
            >
              {t.icon(tab === t.key)}
              <span>{t.label}</span>
            </button>
          ))}
        </div>
      </nav>
    </div>
  );
}
