import { useEffect, useRef, useState } from "react";
import {
  BatteryWarning, ChevronDown, Construction, Pause, Play, PlugZap, RotateCcw, SkipForward, Siren, TrafficCone, Wrench, Zap,
} from "lucide-react";
import { useSim } from "../../lib/simulation/store";
import { useCommands } from "../../hooks/useCommands";
import { ALGORITHM_ORDER, ALGORITHM_SHORT } from "../../lib/theme";

const SPEEDS = [0.5, 1, 2, 4, 8];

export function MapControls() {
  const status = useSim((s) => s.status);
  const tool = useSim((s) => s.tool);
  const setTool = useSim((s) => s.setTool);
  const cmd = useCommands();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const running = status?.running ?? false;

  useEffect(() => {
    const close = (e: MouseEvent) => { if (!menuRef.current?.contains(e.target as Node)) setOpen(false); };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, []);

  const pick = (fn: () => void) => { setOpen(false); fn(); };

  return (
    <div className="overlay glass controls">
      <button className={`btn ${running ? "" : "primary"}`} onClick={cmd.toggle} style={{ width: 84 }}
              data-tip={running ? "Pause (Space)" : "Start (Space)"}>
        {running ? <Pause /> : <Play />}{running ? "Pause" : "Start"}
      </button>
      <button className="btn icon" onClick={() => cmd.step(4)} disabled={running} data-tip="Step 2 s (S)"><SkipForward /></button>
      <button className="btn icon" onClick={() => cmd.reset()} data-tip="Reset scenario (Shift+R)"><RotateCcw /></button>
      <div className="divider" />
      <span className="label">Speed</span>
      <div className="seg" role="radiogroup" aria-label="Simulation speed">
        {SPEEDS.map((s, i) => (
          <button key={s} className={status?.speed === s ? "on" : ""} onClick={() => cmd.speed(s)}
                  data-tip={`${s}× (${i + 1})`} role="radio" aria-checked={status?.speed === s}>{s}×</button>
        ))}
      </div>
      <div className="divider" />
      <span className="label">Planner</span>
      <select className="select" value={status?.algorithm ?? "astar"} onChange={(e) => cmd.algorithm(e.target.value)}
              aria-label="Path planning algorithm" style={{ width: 98 }}>
        {ALGORITHM_ORDER.map((a) => <option key={a} value={a}>{ALGORITHM_SHORT[a]}</option>)}
      </select>
      <div className="divider" />
      <div className="inject" ref={menuRef}>
        <button className={`btn ${open || tool ? "active" : ""}`} onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          <Zap />Inject event<ChevronDown style={{ width: 12, height: 12 }} />
        </button>
        {open && (
          <div className="menu" role="menu">
            <div className="menu-label eyebrow">Environment</div>
            <button onClick={() => pick(() => setTool("block"))}>
              <Construction /><span>Block a road…<small>Pick any road on the map. Affected robots replan.</small></span>
            </button>
            <button onClick={() => pick(() => cmd.inject({ type: "ROAD_BLOCKED" }, "Closed a road on the busiest active route"))}>
              <Construction /><span>Block road on an active route<small>Closes a road a few segments ahead of a driving robot.</small></span>
            </button>
            <button onClick={() => pick(() => setTool("traffic"))}>
              <TrafficCone /><span>Congest a corridor…<small>Pick a road; it and two neighbours jam.</small></span>
            </button>
            <div className="menu-label eyebrow">Orders & fleet</div>
            <button onClick={() => pick(() => cmd.inject({ type: "NEW_ORDER", priority: "CRITICAL" }, "CRITICAL order created"))}>
              <Siren /><span>CRITICAL order<small>Watch the allocator score the fleet — it may preempt.</small></span>
            </button>
            <button onClick={() => pick(() => cmd.inject({ type: "ROBOT_LOW_BATTERY", level: 0.14 }, "Battery fault injected"))}>
              <BatteryWarning /><span>Battery fault<small>A busy robot's charge drops to 14 %.</small></span>
            </button>
            <button onClick={() => pick(() => cmd.inject({ type: "ROBOT_FAILURE", duration_s: 240 }, "Robot taken offline"))}>
              <Wrench /><span>Robot failure<small>Offline for 4 min; unpicked orders return to the queue.</small></span>
            </button>
            <button onClick={() => pick(() => cmd.inject({ type: "CHARGING_STATION_BUSY", duration_s: 300 }, "Charging station unavailable"))}>
              <PlugZap /><span>Charger unavailable<small>Busiest station closes for 5 min; robots reroute.</small></span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export function ToolHint() {
  const tool = useSim((s) => s.tool);
  const setTool = useSim((s) => s.setTool);
  if (!tool) return null;
  return (
    <div className="overlay glass toolhint" style={tool === "traffic" ? { borderColor: "rgba(229,121,59,0.45)" } : undefined}>
      {tool === "block" ? <Construction style={{ width: 15, color: "var(--crit)" }} /> : <TrafficCone style={{ width: 15, color: "var(--serious)" }} />}
      <span>{tool === "block" ? "Click a road to close it" : "Click a road to congest its corridor"}</span>
      <span className="muted">·</span>
      <button className="btn sm ghost" onClick={() => setTool(null)}>Cancel <span className="kbd">Esc</span></button>
    </div>
  );
}
