import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { BarChart3, Compass, GitCompareArrows, Gem, Home, Map as MapIcon, Menu, Microscope, Sparkles, TrendingUp, X } from "lucide-react";
import { useCompare } from "../hooks/useCompare";
import Landmark from "./Landmark";

const links = [
  { to: "/", label: "Overview", icon: Home, end: true },
  { to: "/explore", label: "Explore Map", icon: MapIcon },
  { to: "/hidden-gems", label: "Hidden Gems", icon: Gem },
  { to: "/analytics", label: "Sentiment Insights", icon: BarChart3 },
  { to: "/popular", label: "Popular", icon: TrendingUp },
  { to: "/new", label: "Newly Discovered", icon: Sparkles },
  { to: "/compare", label: "Compare", icon: GitCompareArrows },
  { to: "/methodology", label: "Methodology & Data", icon: Microscope },
];

export function Logo() {
  return (
    <Link to="/" className="flex flex-col items-center text-center" aria-label="FoodSpotter home">
      <svg viewBox="0 0 48 52" className="h-12 w-11" aria-hidden>
        <path d="M24 2C13 2 5 10 5 20c0 12 19 30 19 30s19-18 19-30C43 10 35 2 24 2z" fill="#B8441C" />
        <path d="M17 11v9c0 2 1.4 3.4 3.4 3.4V36h2.2V23.4C24.6 23.4 26 22 26 20v-9h-1.8v7h-1.3v-7h-1.8v7h-1.3v-7zM31 11c-2.4 1.4-3.6 4.2-3.6 8 0 2.2.9 3.6 2.4 4.1V36H32V11z" fill="#FAF5EA" />
      </svg>
      <span className="mt-1 font-display text-[1.65rem] font-extrabold leading-none tracking-tight text-leaf-dark">FoodSpotter</span>
      <span className="mt-1.5 text-[12px] leading-snug text-muted">Bengaluru’s restaurants,<br />decoded by reviews</span>
    </Link>
  );
}

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  const { ids } = useCompare();
  return (
    <nav aria-label="Main" className="mt-7 flex flex-col gap-1">
      {links.map(({ to, label, icon: Icon, end }) => (
        <NavLink key={to} to={to} end={end} onClick={onNavigate}
          className={({ isActive }) => `flex items-center gap-3.5 rounded-xl px-4 py-2.5 text-[15px] font-medium transition-colors ${isActive ? "bg-leaf-soft text-leaf-dark" : "text-ink hover:bg-leaf-soft/60"}`}>
          <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden />
          <span>{label}</span>
          {to === "/compare" && ids.length > 0 && <span className="ml-auto rounded-full bg-chili px-1.5 text-xs font-bold text-white" aria-label={`${ids.length} selected`}>{ids.length}</span>}
        </NavLink>
      ))}
    </nav>
  );
}

function SidebarBody({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col px-4 pb-5 pt-6">
      <Logo />
      <Nav onNavigate={onNavigate} />
      <div className="mt-auto pt-6">
        <Landmark className="mx-auto w-[88%] max-w-[230px]" />
        <p className="mt-2 text-center font-script text-[1.65rem] leading-[1.05] text-leaf-dark -rotate-6">Every review,<br />read closely.</p>
        <svg viewBox="0 0 120 10" className="mx-auto mt-1 h-2 w-24 -rotate-3" aria-hidden><path d="M2 7C30 2 80 2 118 6" stroke="#B8441C" strokeWidth="1.5" fill="none" strokeLinecap="round" /></svg>
      </div>
    </div>
  );
}

export default function Layout() {
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  useEffect(() => setOpen(false), [loc.pathname]);
  return (
    <div className="min-h-screen lg:pl-[250px]">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-[3000] focus:rounded focus:bg-white focus:px-3 focus:py-2">Skip to content</a>
      <aside className="fixed inset-y-0 left-0 z-[1200] hidden w-[250px] overflow-y-auto border-r border-line bg-sidebar lg:block" aria-label="Sidebar">
        <SidebarBody />
      </aside>

      <header className="sticky top-0 z-[1200] flex items-center justify-between border-b border-line bg-sidebar/95 px-4 py-2.5 backdrop-blur lg:hidden">
        <Link to="/" className="flex items-center gap-2" aria-label="FoodSpotter home">
          <Compass className="h-6 w-6 text-chili" aria-hidden /><span className="font-display text-xl font-extrabold text-leaf-dark">FoodSpotter</span>
        </Link>
        <button className="btn btn-ghost px-2.5" aria-expanded={open} aria-controls="drawer" aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen((o) => !o)}>
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </header>
      {open && (
        <div className="fixed inset-0 z-[1300] lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <button className="absolute inset-0 bg-ink/40" aria-label="Close menu" onClick={() => setOpen(false)} tabIndex={-1} />
          <div id="drawer" className="absolute inset-y-0 left-0 w-[270px] max-w-[85vw] overflow-y-auto bg-sidebar shadow-lift"><SidebarBody onNavigate={() => setOpen(false)} /></div>
        </div>
      )}

      <main id="main" className="min-w-0"><Outlet /></main>
      <footer className="border-t border-line px-5 py-4 text-center text-xs leading-relaxed text-muted">
        Restaurant locations © <a className="underline" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>.
        Reviews come from a historical Zomato dataset snapshot (Kaggle) and may be out of date. FoodSpotter is an academic Web &amp; Social Media Analytics project and isn’t affiliated with Zomato, Google or OpenStreetMap.
      </footer>
    </div>
  );
}
