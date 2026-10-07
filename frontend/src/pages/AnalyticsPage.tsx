import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { usePoll } from "../hooks/usePoll";
import { api } from "../lib/api";
import { BarChart, LineChart, StatTile, type BarDatum } from "../components/analytics/charts";
import { ALGORITHM_COLOR, ALGORITHM_ORDER, ALGORITHM_SHORT, ACCENT } from "../lib/theme";
import { clock, compact, duration, ms, num, pct, titleCase } from "../lib/formatters";
import type { AlgorithmKey, Experiment } from "../lib/types";

const RANGES = [
  { key: "300", label: "Last 5 min", s: 300 },
  { key: "900", label: "Last 15 min", s: 900 },
  { key: "1800", label: "Last 30 min", s: 1800 },
  { key: "all", label: "Whole run", s: Infinity },
];

const COMPARISONS: { key: string; title: string; unit: string; fmt: (v: number) => string; lowerBetter: boolean }[] = [
  { key: "avg_route_cost", title: "Average path cost", unit: "s travel time", fmt: (v) => num(v, 0), lowerBetter: true },
  { key: "avg_nodes_explored", title: "Nodes explored per search", unit: "expansions", fmt: (v) => num(v, 0), lowerBetter: true },
  { key: "avg_planning_ms", title: "Execution time per search", unit: "ms", fmt: (v) => v.toFixed(2), lowerBetter: true },
  { key: "average_delivery_time", title: "Delivery completion time", unit: "s", fmt: (v) => duration(v), lowerBetter: true },
  { key: "energy_per_delivery_wh", title: "Energy per delivery", unit: "Wh", fmt: (v) => num(v, 0), lowerBetter: true },
  { key: "robot_utilization", title: "Robot utilisation", unit: "", fmt: (v) => pct(v), lowerBetter: false },
];

export function AnalyticsPage() {
  const { data: m } = usePoll(() => api.metrics(), [], 3000);
  const { data: experiments } = usePoll(() => api.experiments(), [], 10000);
  const [range, setRange] = useState("all");
  const [scenario, setScenario] = useState("all");
  const [expId, setExpId] = useState<string>("");
  const [algo, setAlgo] = useState<"all" | AlgorithmKey>("all");
  const [robot, setRobot] = useState("all");
  const [exp, setExp] = useState<Experiment | null>(null);

  const completed = (experiments ?? []).filter((e) => e.status === "completed" && (scenario === "all" || e.scenario_key === scenario));
  const scenarios = [...new Set((experiments ?? []).map((e) => e.scenario_key))];
  useEffect(() => {
    if (!completed.length) { setExp(null); return; }
    const id = completed.some((e) => e.id === expId) ? expId : completed[0].id;
    if (id !== expId) setExpId(id);
    api.experiment(id).then(setExp).catch(() => setExp(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expId, experiments, scenario]);

  const span = RANGES.find((r) => r.key === range)!.s;
  const ts = useMemo(() => {
    const samples = m?.timeseries ?? [];
    const end = samples.length ? samples[samples.length - 1].t : 0;
    return samples.filter((s) => s.t >= end - span);
  }, [m, span]);

  const g = m?.global;
  const robots = (m?.robots ?? []).filter((r) => robot === "all" || r.id === robot);
  const algos = (exp?.algorithms ?? ALGORITHM_ORDER).filter((a) => algo === "all" || a === algo);

  return (
    <div className="page"><div className="page-inner">
      <div className="page-head">
        <div>
          <h1>Analytics</h1>
          <p>Live metrics of the running simulation, and algorithm comparisons from controlled experiments. Every value is measured, nothing is estimated.</p>
        </div>
      </div>

      <div className="card filters">
        <span className="eyebrow">Filters</span>
        <label className="inline-field">Scenario
          <select className="select" value={scenario} onChange={(e) => setScenario(e.target.value)}>
            <option value="all">All scenarios</option>
            {scenarios.map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
          </select></label>
        <label className="inline-field">Experiment
          <select className="select" value={expId} onChange={(e) => setExpId(e.target.value)} disabled={!completed.length} style={{ maxWidth: 260 }}>
            {!completed.length && <option>None yet</option>}
            {completed.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select></label>
        <label className="inline-field">Algorithm
          <select className="select" value={algo} onChange={(e) => setAlgo(e.target.value as any)}>
            <option value="all">All</option>
            {ALGORITHM_ORDER.map((a) => <option key={a} value={a}>{ALGORITHM_SHORT[a]}</option>)}
          </select></label>
        <label className="inline-field">Robot
          <select className="select" value={robot} onChange={(e) => setRobot(e.target.value)}>
            <option value="all">All robots</option>
            {(m?.robots ?? []).map((r) => <option key={r.id} value={r.id}>{r.id}</option>)}
          </select></label>
        <label className="inline-field">Time range
          <select className="select" value={range} onChange={(e) => setRange(e.target.value)}>
            {RANGES.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
          </select></label>
      </div>

      <div className="eyebrow" style={{ margin: "4px 0 10px" }}>Current run · {m ? `${titleCase(m.scenario.key)} · seed ${m.scenario.seed} · T+${clock(g?.t ?? 0)}` : "loading"}</div>
      <div className="grid g4" style={{ marginBottom: 14 }}>
        <StatTile label="Deliveries" value={g ? `${g.orders_delivered}` : "—"} unit={g ? `/ ${g.orders_created}` : ""}
                  detail={g ? `${pct(g.completion_rate)} completion · ${pct(g.on_time_rate)} on time` : null} />
        <StatTile label="Avg delivery time" value={duration(g?.avg_delivery_time)}
                  detail={g?.p90_delivery_time ? `p90 ${duration(g.p90_delivery_time)} · wait to assign ${duration(g.avg_assignment_wait)}` : "creation → hand-over"} />
        <StatTile label="Energy used" value={g ? num(g.total_energy_kwh, 2) : "—"} unit="kWh"
                  detail={g ? `${num(g.energy_per_delivery_wh, 0)} Wh per delivery · ${num(g.total_distance_km, 1)} km driven` : null} />
        <StatTile label="Replans" value={g ? `${g.replans}` : "—"}
                  detail={g ? Object.entries(g.replan_triggers).map(([k, v]) => `${v} ${titleCase(k)}`).join(" · ") || "none yet" : null} />
      </div>

      <div className="grid g2" style={{ marginBottom: 14 }}>
        <div className="card">
          <div className="card-head"><h3>Orders over time</h3><p>simulated time</p></div>
          <div className="card-body">
            <LineChart height={210} formatX={clock} formatY={(v) => compact(v)} yLabel="orders"
                       series={[
                         { key: "delivered", label: "Delivered", color: "#3987e5", points: ts.map((s) => ({ x: s.t, y: s.delivered })) },
                         { key: "open", label: "Open", color: "#d95926", points: ts.map((s) => ({ x: s.t, y: s.open })) },
                       ]} />
          </div>
        </div>
        <div className="card">
          <div className="card-head"><h3>Fleet energy consumed</h3><p>cumulative, kWh</p></div>
          <div className="card-body">
            <LineChart height={210} area formatX={clock} formatY={(v) => (v / 1000).toFixed(1)}
                       series={[{ key: "energy", label: "Energy", color: ACCENT, points: ts.map((s) => ({ x: s.t, y: s.energy_wh })) }]} />
          </div>
        </div>
      </div>

      <div className="grid g2" style={{ marginBottom: 22 }}>
        <div className="card">
          <div className="card-head"><h3>Robot utilisation</h3><p>share of time spent on deliveries</p></div>
          <div className="card-body">
            <BarChart format={(v) => pct(v)} data={robots.map((r) => ({
              key: r.id, label: r.id, value: r.utilization, color: ACCENT, highlight: robot === r.id,
            }))} />
          </div>
        </div>
        <div className="card">
          <div className="card-head"><h3>Planner telemetry · current run</h3><p>from every search the fleet executed</p></div>
          <div className="card-body" style={{ padding: 0 }}>
            <table className="data">
              <thead><tr><th>Algorithm</th><th>Searches</th><th>Nodes / search</th><th>Time / search</th><th>Avg cost</th><th>Success</th></tr></thead>
              <tbody>
                {Object.entries(m?.algorithms ?? {}).map(([k, s]) => (
                  <tr key={k}>
                    <td><i className="swatch" style={{ background: ALGORITHM_COLOR[k as AlgorithmKey] }} />{ALGORITHM_SHORT[k as AlgorithmKey]}</td>
                    <td>{s.searches}<span className="sd">+{s.cache_hits} cached</span></td>
                    <td>{num(s.avg_nodes_explored, 1)}</td>
                    <td>{ms(s.avg_planning_ms)}</td>
                    <td>{num(s.avg_route_cost, 0)} s</td>
                    <td>{pct(s.success_rate, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {robot !== "all" && robots[0] && (
              <div style={{ padding: 14, borderTop: "1px solid var(--line)" }}>
                <div className="eyebrow" style={{ marginBottom: 8 }}>{robots[0].id} · {robots[0].model}</div>
                <dl className="kv">
                  <dt>Orders completed</dt><dd>{robots[0].orders_completed}</dd>
                  <dt>Distance</dt><dd>{robots[0].distance_km.toFixed(2)} km</dd>
                  <dt>Energy</dt><dd>{num(robots[0].energy_wh)} Wh</dd>
                  <dt>Active / idle / charging</dt><dd>{duration(robots[0].busy_time)} / {duration(robots[0].idle_time)} / {duration(robots[0].charging_time)}</dd>
                  <dt>Replans</dt><dd>{robots[0].replans}</dd>
                </dl>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="page-head" style={{ marginBottom: 12 }}>
        <div>
          <h1 style={{ fontSize: 15 }}>Algorithm comparison</h1>
          <p>{exp ? `${exp.name} · ${exp.repetitions} repetition${exp.repetitions > 1 ? "s" : ""} × ${duration(exp.duration_s)} simulated · bars show the mean, whiskers ±1 std` :
            "Run an experiment to compare algorithms under identical conditions."}</p>
        </div>
        <div className="actions"><Link className="btn" to="/experiments">Open experiments</Link></div>
      </div>
      {exp?.aggregates ? (
        <div className="grid g3">
          {COMPARISONS.map((c) => {
            const data: BarDatum[] = algos.map((a) => {
              const st = exp.aggregates![a]?.[c.key];
              return { key: a, label: ALGORITHM_SHORT[a], value: st?.mean ?? null, spread: st?.std ?? null, color: ALGORITHM_COLOR[a] };
            });
            return (
              <div className="card" key={c.key}>
                <div className="card-head"><h3>{c.title}</h3><p>{c.lowerBetter ? "lower is better" : "higher is better"}</p></div>
                <div className="card-body"><BarChart data={data} format={c.fmt} unit={c.unit} /></div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="card empty"><strong>No completed experiments{scenario !== "all" ? " for this scenario" : ""}</strong>
          Experiments run every algorithm on the same seed, fleet, orders and incidents.</div>
      )}
    </div></div>
  );
}
