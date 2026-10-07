import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { Activity, BarChart3, CheckCircle2, FlaskConical, Map, Network, SlidersHorizontal, XCircle, Info } from "lucide-react";
import { useSim } from "../../lib/simulation/store";
import { api } from "../../lib/api";
import { clock } from "../../lib/formatters";
import { ALGORITHM_SHORT } from "../../lib/theme";
import type { Health } from "../../lib/types";

function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="7" fill="#10161d" stroke="rgba(148,163,184,0.18)" />
      <path d="M8 22 L14 10 L18 17 L24 9" fill="none" stroke="#4fd6c4" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="8" cy="22" r="2.4" fill="#4fd6c4" />
      <circle cx="24" cy="9" r="2.4" fill="#e6ebf1" />
    </svg>
  );
}

function Toasts() {
  const toasts = useSim((s) => s.toasts);
  const dismiss = useSim((s) => s.dismissToast);
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.tone}`} onClick={() => dismiss(t.id)} role="status">
          {t.tone === "error" ? <XCircle style={{ color: "var(--crit)" }} /> : t.tone === "success" ? <CheckCircle2 style={{ color: "var(--ok)" }} /> : <Info />}
          <span>{t.message}</span>
        </div>
      ))}
    </div>
  );
}

export function AppShell() {
  const status = useSim((s) => s.status);
  const t = useSim((s) => s.snapshot?.t ?? 0);
  const connection = useSim((s) => s.connection);
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    const load = () => api.health().then(setHealth).catch(() => setHealth(null));
    load();
    const id = window.setInterval(load, 15000);
    return () => window.clearInterval(id);
  }, []);

  const running = status?.running;
  const db = health?.database;
  const dbClass = !db?.connected ? "bad" : db.fallback ? "warn" : "";
  const dbText = !db ? "API offline" : !db.connected ? "No persistence" : db.fallback ? `${db.dialect} (fallback)` : db.dialect === "postgresql" ? "PostgreSQL" : db.dialect;
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand"><BrandMark />FleetMind <small>v1</small></div>
        <nav className="nav">
          <NavLink to="/" end><Map />Operations</NavLink>
          <NavLink to="/analytics"><BarChart3 />Analytics</NavLink>
          <NavLink to="/experiments"><FlaskConical />Experiments</NavLink>
          <NavLink to="/algorithms"><Network />Algorithms</NavLink>
          <NavLink to="/scenarios"><SlidersHorizontal />Scenarios</NavLink>
        </nav>
        <div className="topbar-right">
          {status && (
            <span className="chip" title={status.scenario.description}>
              {status.scenario.name} <span className="muted">·</span> seed <span className="mono">{status.scenario.seed}</span>
              <span className="muted">·</span> <span className="mono">{ALGORITHM_SHORT[status.algorithm]}</span>
            </span>
          )}
          <span className="sep" />
          <span className="run-state" aria-live="polite">
            <span className={`run-dot ${running ? "live" : "paused"}`} />
            <span style={{ color: running ? "var(--text-0)" : "var(--warn)" }}>{running ? "SIMULATION RUNNING" : "PAUSED"}</span>
          </span>
          <span className="clock"><small>T+</small>{clock(t)}</span>
          <span className="sep" />
          <span className={`conn ${connection !== "open" ? "bad" : ""}`} title="Real-time channel">
            <i /><Activity style={{ width: 12 }} />{connection === "open" ? `${status?.speed ?? 1}×` : connection}
          </span>
          <span className={`conn ${dbClass}`} title={db?.url ?? "Database"}><i />{dbText}</span>
        </div>
      </header>
      <main style={{ minHeight: 0 }}><Outlet /></main>
      <Toasts />
    </div>
  );
}
