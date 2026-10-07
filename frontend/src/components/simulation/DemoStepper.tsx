import { useSim } from "../../lib/simulation/store";
import { duration, ms, num, pct } from "../../lib/formatters";
import { Play } from "lucide-react";
import { Link } from "react-router-dom";
import { useCommands } from "../../hooks/useCommands";

/** Guided-demo narration: which phase is active, what it shows, and when the next one starts. */
export function DemoStepper() {
  const demo = useSim((s) => s.snapshot?.demo ?? null);
  const running = useSim((s) => s.status?.running ?? false);
  const t = useSim((s) => s.snapshot?.t ?? 0);
  const k = useSim((s) => s.snapshot?.kpis);
  const cmd = useCommands();
  if (!demo) return null;
  const idx = Math.max(0, demo.index);
  const phase = demo.phases[idx];
  if (t === 0 && !running) return null;
  return (
    <div className="overlay glass demo" aria-live="polite">
      <div className="demo-steps">
        {demo.phases.map((p, i) => (
          <div key={p.key} className={`demo-step ${i < idx ? "done" : i === idx ? "active" : ""}`} title={p.title} />
        ))}
      </div>
      <div className="demo-head demo-enter" key={phase.key}>
        <span className="eyebrow">Phase {idx + 1} / {demo.phases.length}</span>
        <h3>{phase.title}</h3>
        <span className="when">
          {demo.complete ? "demo complete" : demo.next_in != null ? `next phase in ${duration(demo.next_in)} sim` : "waiting for replan"}
        </span>
      </div>
      <p className="demo-enter" key={phase.key + "p"}>
        {phase.description}
        {phase.note && <> <span className="note">— {phase.note}</span></>}
      </p>
      {demo.complete && k && (
        <div className="grid g4" style={{ gap: 1, marginTop: 10, background: "var(--line)", border: "1px solid var(--line)", borderRadius: 4, overflow: "hidden" }}>
          {[
            ["Delivered", `${k.orders_delivered} / ${k.orders_created}`],
            ["On time", pct(k.on_time_rate)],
            ["Avg delivery", duration(k.avg_delivery_time)],
            ["Energy", `${k.total_energy_kwh.toFixed(2)} kWh`],
            ["Replans", `${k.replans}`],
            ["Preemptions", `${k.preemptions}`],
            ["Nodes / search", num(k.avg_nodes_explored, 0)],
            ["Plan time", ms(k.avg_planning_ms)],
          ].map(([label, value]) => (
            <div key={label} style={{ background: "var(--bg-1)", padding: "6px 9px" }}>
              <div className="muted" style={{ fontSize: 10.5 }}>{label}</div>
              <div className="mono" style={{ fontSize: 13 }}>{value}</div>
            </div>
          ))}
        </div>
      )}
      {demo.complete && !running && (
        <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
          <button className="btn sm" onClick={() => cmd.start()}><Play />Keep running</button>
          <Link className="btn sm ghost" to="/analytics">Open analytics →</Link>
        </div>
      )}
    </div>
  );
}
