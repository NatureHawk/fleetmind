import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Dices, FlaskConical, Play } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { useSim } from "../lib/simulation/store";
import { useCommands } from "../hooks/useCommands";
import { ALGORITHM_ORDER, ALGORITHM_SHORT, PRIORITY_COLOR } from "../lib/theme";
import { duration, pct } from "../lib/formatters";
import type { Priority, ScenarioConfig } from "../lib/types";

function Slider({ label, value, min, max, step = 1, onChange, fmt = (v: number) => String(v), hint }: {
  label: string; value: number; min: number; max: number; step?: number; onChange: (v: number) => void;
  fmt?: (v: number) => string; hint?: ReactNode;
}) {
  return (
    <div className="field">
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <span className="label">{label}</span><span className="mono" style={{ fontSize: 11.5 }}>{fmt(value)}</span>
      </div>
      <input type="range" className="range" min={min} max={max} step={step} value={value}
             onChange={(e) => onChange(Number(e.target.value))} aria-label={label} />
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}

export function ScenariosPage() {
  const status = useSim((s) => s.status);
  const toast = useSim((s) => s.toast);
  const cmd = useCommands();
  const navigate = useNavigate();
  const [presets, setPresets] = useState<ScenarioConfig[]>([]);
  const [selected, setSelected] = useState<string>("baseline");
  const [cfg, setCfg] = useState<ScenarioConfig | null>(null);

  useEffect(() => {
    api.scenarios().then((list) => {
      setPresets(list);
      const cur = list.find((s) => s.key === status?.scenario.key) ?? list[1];
      setSelected(cur.key);
      setCfg({ ...cur, seed: status?.scenario.seed ?? cur.seed });
    }).catch(() => toast("Could not load scenarios", "error"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const choose = (s: ScenarioConfig) => { setSelected(s.key); setCfg({ ...s, seed: cfg?.seed ?? s.seed }); };
  // Changing a run setting keeps the preset; changing anything that shapes the world makes it a custom scenario.
  const RUN_SETTINGS: (keyof ScenarioConfig)[] = ["seed", "algorithm", "heuristic", "speed"];
  const set = <K extends keyof ScenarioConfig>(k: K, v: ScenarioConfig[K]) => {
    if (!cfg) return;
    const custom = RUN_SETTINGS.includes(k) || cfg.key === "custom" ? {} : { key: "custom", name: `Custom · ${cfg.name}` };
    setCfg({ ...cfg, [k]: v, ...custom });
  };

  const load = async () => {
    if (!cfg) return;
    const res = await cmd.reset({ config: cfg });
    if (res) { toast(`Loaded ${cfg.name} (seed ${cfg.seed})`, "success"); navigate("/"); }
  };
  const experiment = async () => {
    if (!cfg) return;
    try {
      const job = await api.runExperiment({ config: { ...cfg, demo: false }, algorithms: [...ALGORITHM_ORDER], repetitions: 1,
                                            duration_s: Math.max(300, Math.min(7200, cfg.duration_s)) });
      navigate(`/experiments?id=${job.id}`);
    } catch (e) { toast(e instanceof ApiError ? e.message : "Could not start experiment", "error"); }
  };

  const weights = cfg?.priority_weights;
  const wsum = weights ? Object.values(weights).reduce((a, b) => a + b, 0) || 1 : 1;
  return (
    <div className="page"><div className="page-inner">
      <div className="page-head">
        <div>
          <h1>Scenarios</h1>
          <p>Each scenario plus a seed fully determines a run: the city, the fleet, every delivery request and every incident. Pick a preset or tune one in the builder.</p>
        </div>
      </div>

      <div className="grid g3" style={{ marginBottom: 18 }}>
        {presets.map((s) => (
          <div key={s.key} className={`card scenario-card ${selected === s.key ? "sel" : ""}`} onClick={() => choose(s)} role="button" tabIndex={0}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <h3>{s.name}</h3>
              {s.demo && <span className="badge soft" style={{ color: "var(--accent)" }}>presentation</span>}
              {status?.scenario.key === s.key && <span className="badge soft" style={{ color: "var(--ok)", marginLeft: "auto" }}><i />loaded</span>}
            </div>
            <p>{s.description}</p>
            <div className="purpose">Purpose — {s.purpose}</div>
            <div className="facts">
              <span>{s.robots} robots</span><span>{s.order_rate_per_min}/min</span>
              <span>traffic {pct(s.traffic_intensity)}</span>
              {s.closure_events > 0 && <span>{s.closure_events} closures</span>}
              {s.congestion_events > 0 && <span>{s.congestion_events} jams</span>}
              {s.low_battery_robots > 0 && <span>{s.low_battery_robots} low batt.</span>}
            </div>
          </div>
        ))}
      </div>

      {cfg && (
        <div className="card">
          <div className="card-head">
            <h3>Scenario builder</h3><p>starting from “{presets.find((p) => p.key === selected)?.name}”</p>
            <div className="right">
              <button className="btn" onClick={experiment}><FlaskConical />Compare all algorithms</button>
              <button className="btn primary" onClick={load}><Play />Load into simulation</button>
            </div>
          </div>
          <div className="card-body">
            <div className="grid g4" style={{ gap: 22 }}>
              <div className="grid" style={{ gap: 14, alignContent: "start" }}>
                <div className="eyebrow">Fleet</div>
                <Slider label="Number of robots" value={cfg.robots} min={1} max={50} onChange={(v) => set("robots", v)} />
                <Slider label="Initial battery (min)" value={cfg.battery_min} min={0.05} max={1} step={0.05} fmt={(v) => pct(v)}
                        onChange={(v) => set("battery_min", Math.min(v, cfg.battery_max))} />
                <Slider label="Initial battery (max)" value={cfg.battery_max} min={0.05} max={1} step={0.05} fmt={(v) => pct(v)}
                        onChange={(v) => set("battery_max", Math.max(v, cfg.battery_min))} />
                <Slider label="Robots starting critically low" value={cfg.low_battery_robots} min={0} max={cfg.robots}
                        onChange={(v) => set("low_battery_robots", v)} hint="start between 14 % and 26 %" />
              </div>
              <div className="grid" style={{ gap: 14, alignContent: "start" }}>
                <div className="eyebrow">Orders</div>
                <Slider label="Number of orders (total)" value={cfg.max_orders} min={10} max={600} step={10} onChange={(v) => set("max_orders", v)} />
                <Slider label="Initial backlog" value={cfg.initial_orders} min={0} max={120} onChange={(v) => set("initial_orders", v)} />
                <Slider label="Arrival rate" value={cfg.order_rate_per_min} min={0} max={12} step={0.1} fmt={(v) => `${v.toFixed(1)}/min`}
                        onChange={(v) => set("order_rate_per_min", v)} />
                <div className="field">
                  <span className="label">Priority distribution</span>
                  {(["LOW", "NORMAL", "HIGH", "CRITICAL"] as Priority[]).map((p) => (
                    <div key={p} style={{ display: "grid", gridTemplateColumns: "70px 1fr 40px", gap: 8, alignItems: "center" }}>
                      <span style={{ fontSize: 11 }}><span className="prio" style={{ background: PRIORITY_COLOR[p] }} />{p}</span>
                      <input type="range" className="range" min={0} max={1} step={0.05} value={weights![p]}
                             onChange={(e) => set("priority_weights", { ...weights!, [p]: Number(e.target.value) })} aria-label={`${p} weight`} />
                      <span className="mono muted" style={{ fontSize: 11, textAlign: "right" }}>{pct(weights![p] / wsum)}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="grid" style={{ gap: 14, alignContent: "start" }}>
                <div className="eyebrow">Environment</div>
                <Slider label="Traffic intensity" value={cfg.traffic_intensity} min={0} max={0.6} step={0.01} fmt={(v) => pct(v)}
                        onChange={(v) => set("traffic_intensity", v)} hint="share of roads congested at start" />
                <Slider label="Congestion events" value={cfg.congestion_events} min={0} max={30} onChange={(v) => set("congestion_events", v)} />
                <Slider label="Road closures" value={cfg.closure_events} min={0} max={30} onChange={(v) => set("closure_events", v)} />
                <Slider label="Road failure probability" value={cfg.road_failure_probability} min={0} max={0.5} step={0.01}
                        fmt={(v) => `${pct(v)}/min`} onChange={(v) => set("road_failure_probability", v)} hint="extra random closures per minute" />
                <Slider label="Robot failures" value={cfg.robot_failures} min={0} max={10} onChange={(v) => set("robot_failures", v)} />
              </div>
              <div className="grid" style={{ gap: 14, alignContent: "start" }}>
                <div className="eyebrow">Run</div>
                <div className="field"><label>Search algorithm</label>
                  <select className="select" value={cfg.algorithm} onChange={(e) => set("algorithm", e.target.value as any)}>
                    {ALGORITHM_ORDER.map((a) => <option key={a} value={a}>{ALGORITHM_SHORT[a]}</option>)}
                  </select></div>
                <div className="field"><label>Heuristic (Greedy, A*)</label>
                  <select className="select" value={cfg.heuristic} onChange={(e) => set("heuristic", e.target.value)}>
                    <option value="euclidean">Euclidean (admissible)</option>
                    <option value="manhattan">Manhattan (not admissible here)</option>
                    <option value="zero">Zero (A* = Dijkstra)</option>
                  </select></div>
                <div className="field"><label>Random seed</label>
                  <div style={{ display: "flex", gap: 6 }}>
                    <input className="input mono" type="number" style={{ flex: 1 }} value={cfg.seed} min={0}
                           onChange={(e) => set("seed", Math.max(0, Number(e.target.value) || 0))} />
                    <button className="btn icon" onClick={() => set("seed", Math.floor(Math.random() * 99999))} data-tip="Random seed"><Dices /></button>
                  </div></div>
                <div className="field"><label>Simulation speed</label>
                  <div className="seg">{[0.5, 1, 2, 4, 8].map((s) => (
                    <button key={s} className={cfg.speed === s ? "on" : ""} onClick={() => set("speed", s)}>{s}×</button>
                  ))}</div></div>
                <Slider label="Incident window / experiment length" value={cfg.duration_s} min={300} max={7200} step={300}
                        fmt={(v) => duration(v)} onChange={(v) => set("duration_s", v)} />
                <label className="check"><input type="checkbox" checked={cfg.preemption} onChange={(e) => set("preemption", e.target.checked)} />
                  <span className="box" />Allow CRITICAL orders to preempt</label>
              </div>
            </div>
          </div>
        </div>
      )}
    </div></div>
  );
}
