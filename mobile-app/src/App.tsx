import { Suspense, lazy, useState } from "react";

const Home = lazy(() => import("./tabs/Home"));
const Discover = lazy(() => import("./tabs/Discover"));
const Search = lazy(() => import("./tabs/Search"));
const Activity = lazy(() => import("./tabs/Activity"));

const TABS = [
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

export default function App() {
  const [tab, setTab] = useState<TabKey>("home");

  return (
    <div className="app">
      <main className="main" key={tab}>
        <Suspense fallback={<TabSkeleton />}>
          {tab === "home" && <Home />}
          {tab === "discover" && <Discover />}
          {tab === "search" && <Search />}
          {tab === "activity" && <Activity />}
        </Suspense>
      </main>
      <nav className="tabbar" aria-label="Primary">
        <div className="tabbar-inner">
          {TABS.map((t) => (
            <button
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
