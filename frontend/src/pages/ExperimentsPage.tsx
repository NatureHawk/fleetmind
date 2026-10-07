import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Dices, FlaskConical, ShieldAlert, ShieldCheck, Trash2 } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { useSim } from "../lib/simulation/store";
import { BarChart, LineChart } from "../components/analytics/charts";
import { ALGORITHM_COLOR, ALGORITHM_ORDER, ALGORITHM_SHORT } from "../lib/theme";
import { clock, duration, ms, num, pct, titleCase } from "../lib/formatters";
import type { AlgorithmKey, Experiment, MetricStat, ScenarioConfig } from "../lib/types";

interface Column { key: string; label: string; fmt: (v: number) => string; better: "low" | "high" | null }
const COLUMNS: Column[] = [
  { key: "deliveries_completed", label: "Delivered", fmt: (v) => num(v, v % 1 ? 1 : 0), better: "high" },
  { key: "deliveries_failed", label: "Failed", fmt: (v) => num(v, v % 1 ? 1 : 0), better: "low" },
  { key: "on_time_rate", label: "On time", fmt: (v) => pct(v), better: "high" },
  { key: "average_delivery_time", label: "Avg delivery", fmt: (v) => duration(v), better: "low" },
  { key: "avg_route_cost", label: "Path cost", fmt: (v) => `${num(v, 1)} s`, better: "low" },
  { key: "avg_nodes_explored", label: "Nodes / search", fmt: (v) => num(v, 1), better: "low" },
  { key: "avg_planning_ms", label: "Time / search", fmt: (v) => ms(v), better: "low" },
  { key: "energy_per_delivery_wh", label: "Wh / delivery", fmt: (v) => num(v, 0), better: "low" },
  { key: "replans", label: "Replans", fmt: (v) => num(v, v % 1 ? 1 : 0), better: null },
  { key: "robot_utilization", label: "Utilisation", fmt: (v) => pct(v), better: null },
  { key: "battery_depletions", label: "Strandings", fmt: (v) => num(v, v % 1 ? 1 : 0), better: "low" },
];

const DURATIONS = [600, 900, 1800, 3600];

/** Best mean in a column (ties are all highlighted). */
function best(exp: Experiment, col: Column): number | null {
  if (!col.better || !exp.aggregates) return null;
  const vals = Object.values(exp.aggregates).map((agg) => agg[col.key]?.mean).filter((v): v is number => v != null);
  if (!vals.length) return null;
  return col.better === "low" ? Math.min(...vals) : Math.max(...vals);
}

function isTop(v: number | null | undefined, top: number | null): boolean {
  return v != null && top != null && Math.abs(v - top) <= 1e-9 * Math.max(1, Math.abs(top));
}

function Cell({ stat, col, isBest }: { stat?: MetricStat; col: Column; isBest: boolean }) {
  if (!stat || stat.mean == null) return <td className="muted">—</td>;
  return <td className={isBest ? "best" : ""}>{col.fmt(stat.mean)}{stat.n > 1 && stat.std ? <span className="sd">±{col.fmt(stat.std)}</span> : null}</td>;
}

export function ExperimentsPage() {
  const toast = useSim((s) => s.toast);
  const [params, setParams] = useSearchParams();
  const [scenarios, setScenarios] = useState<ScenarioConfig[]>([]);
  const [list, setList] = useState<Experiment[]>([]);
  const [current, setCurrent] = useState<Experiment | null>(null);
  const [scenario, setScenario] = useState("road_closure");
  const [seed, setSeed] = useState(42173);
  const [durationS, setDurationS] = useState(1800);
  const [reps, setReps] = useState(1);
  const [algos, setAlgos] = useState<AlgorithmKey[]>([...ALGORITHM_ORDER]);
  const [busy, setBusy] = useState(false);
  const selectedId = params.get("id");

  const refreshList = () => api.experiments().then(setList).catch(() => {});
  useEffect(() => {
    api.scenarios().then((s) => setScenarios(s.filter((x) => !x.demo))).catch(() => {});
    refreshList();
  }, []);
  useEffect(() => {
    if (!selectedId && list.length) setParams({ id: list[0].id }, { replace: true });
  }, [list, selectedId, setParams]);
  useEffect(() => {
    if (!selectedId) { setCurrent(null); return; }
    let alive = true;
    let timer = 0;
    const load = async () => {
      try {
        const e = await api.experiment(selectedId);
        if (!alive) return;
        setCurrent(e);
        if (e.status === "running") timer = window.setTimeout(load, 700);
        else refreshList();
      } catch { if (alive) setCurrent(null); }
    };
    load();
    return () => { alive = false; window.clearTimeout(timer); };
  }, [selectedId]);

  const run = async () => {
    if (!algos.length) { toast("Select at least one algorithm", "error"); return; }
    setBusy(true);
    try {
      const ordered = ALGORITHM_ORDER.filter((a) => algos.includes(a));
      const job = await api.runExperiment({ scenario, seed, algorithms: ordered, repetitions: reps, duration_s: durationS });
      toast(`Experiment started: ${ordered.length * reps} headless runs`, "success");
      await refreshList();
      setParams({ id: job.id });
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Could not start experiment", "error");
    } finally { setBusy(false); }
  };

  const remove = async (id: string) => {
    await api.deleteExperiment(id).catch(() => {});
    setParams({});
    refreshList();
  };

  const exp = current;
  const order = exp ? ALGORITHM_ORDER.filter((a) => exp.algorithms.includes(a)) : [];
  const deliveriesSeries = useMemo(() => !exp?.results ? [] : order.map((a) => {
    const run = exp.results!.find((r) => r.algorithm === a && r.repetition === 0);
    return { key: a, label: ALGORITHM_SHORT[a], color: ALGORITHM_COLOR[a], points: (run?.timeseries ?? []).map((p) => ({ x: p.t, y: p.delivered })) };
  }), [exp]);
  const coinciding = useMemo(() => {
    const pairs: [AlgorithmKey, AlgorithmKey][] = [];
    deliveriesSeries.forEach((s, i) => deliveriesSeries.slice(i + 1).forEach((t) => {
      if (s.points.length && JSON.stringify(s.points) === JSON.stringify(t.points)) pairs.push([s.key, t.key]);
    }));
    return pairs;
  }, [deliveriesSeries]);
  const sc = scenarios.find((s) => s.key === scenario);

  return (
    <div className="page"><div className="page-inner">
      <div className="page-head">
        <div>
          <h1>Experiments</h1>
          <p>Run one scenario once per algorithm under identical initial conditions — same city, fleet, order stream, incident timeline and seed. Runs execute headless in parallel worker processes; results are persisted.</p>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "300px minmax(0, 1fr)", alignItems: "start" }}>
        <div className="grid">
          <div className="card">
            <div className="card-head"><h3>New experiment</h3></div>
            <div className="card-body grid" style={{ gap: 12 }}>
              <div className="field"><label>Scenario</label>
                <select className="select" value={scenario} onChange={(e) => setScenario(e.target.value)}>
                  {scenarios.map((s) => <option key={s.key} value={s.key}>{s.name}</option>)}
                </select>
                {sc && <span className="hint">{sc.purpose}</span>}
              </div>
              <div className="field"><label>Random seed</label>
                <div style={{ display: "flex", gap: 6 }}>
                  <input className="input mono" style={{ flex: 1 }} type="number" value={seed} min={0}
                         onChange={(e) => setSeed(Math.max(0, Number(e.target.value) || 0))} />
                  <button className="btn icon" data-tip="Random seed" onClick={() => setSeed(Math.floor(Math.random() * 99999))}><Dices /></button>
                </div>
              </div>
              <div className="grid g2" style={{ gap: 8 }}>
                <div className="field"><label>Duration (sim)</label>
                  <select className="select" value={durationS} onChange={(e) => setDurationS(Number(e.target.value))}>
                    {DURATIONS.map((d) => <option key={d} value={d}>{duration(d)}</option>)}
                  </select></div>
                <div className="field"><label>Repetitions</label>
                  <select className="select" value={reps} onChange={(e) => setReps(Number(e.target.value))}>
                    {[1, 2, 3, 4, 5].map((r) => <option key={r} value={r}>{r} seed{r > 1 ? "s" : ""}</option>)}
                  </select></div>
              </div>
              <div className="field"><span className="label">Algorithms</span>
                <div style={{ display: "grid", gap: 7 }}>
                  {ALGORITHM_ORDER.map((a) => (
                    <label key={a} className="check">
                      <input type="checkbox" checked={algos.includes(a)}
                             onChange={(e) => setAlgos(e.target.checked ? [...algos, a] : algos.filter((x) => x !== a))} />
                      <span className="box" /><i className="swatch" style={{ background: ALGORITHM_COLOR[a], margin: 0 }} />{ALGORITHM_SHORT[a]}
                    </label>
                  ))}
                </div>
              </div>
              <button className="btn primary" onClick={run} disabled={busy}><FlaskConical />Run {algos.length * reps} simulations</button>
            </div>
          </div>
          <div className="card">
            <div className="card-head"><h3>History</h3><span className="right muted">{list.length}</span></div>
            <div style={{ maxHeight: 420, overflow: "auto" }}>
              {list.length === 0 && <div className="empty">No experiments yet.</div>}
              {list.map((e) => (
                <div key={e.id} className={`list-item ${e.id === selectedId ? "sel" : ""}`} onClick={() => setParams({ id: e.id })}>
                  <div className="row"><span style={{ fontWeight: 500 }}>{titleCase(e.scenario_key)}</span>
                    <span className="muted mono" style={{ fontSize: 11 }}>seed {e.seed}</span>
                    <span style={{ marginLeft: "auto", fontSize: 10.5, color: e.status === "completed" ? "var(--ok)" : e.status === "failed" ? "var(--crit)" : "var(--warn)" }}>{e.status}</span></div>
                  <div className="meta">{e.algorithms.map((a) => ALGORITHM_SHORT[a]).join(" · ")} · {e.repetitions}× {duration(e.duration_s)}</div>
                  <div className="meta">{e.created_at ? new Date(e.created_at).toLocaleString() : ""}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="grid">
          {!exp && <div className="card empty"><strong>No experiment selected</strong>Configure one on the left — a 30-minute run per algorithm takes a few seconds.</div>}
          {exp && (
            <>
              <div className="card">
                <div className="card-head">
                  <h3>{exp.name}</h3>
                  <p>{exp.repetitions} repetition{exp.repetitions > 1 ? "s" : ""} · {duration(exp.duration_s)} simulated per run · {exp.config.robots} robots</p>
                  <div className="right">
                    <button className="btn ghost sm" onClick={() => remove(exp.id)} data-tip="Delete experiment" data-tip-pos="left"><Trash2 /></button>
                  </div>
                </div>
                <div className="card-body grid" style={{ gap: 12 }}>
                  {exp.status === "running" && (
                    <div>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                        <span className="dim">Running headless simulations…</span>
                        <span className="mono muted">{exp.done ?? 0} / {exp.total ?? exp.algorithms.length * exp.repetitions}</span>
                      </div>
                      <div className={`progress ${!exp.done ? "indeterminate" : ""}`}><span style={{ width: `${exp.progress * 100}%` }} /></div>
                    </div>
                  )}
                  {exp.status === "failed" && <div style={{ color: "var(--crit)" }}>{exp.error}</div>}
                  {exp.fairness && (
                    <div className={`fair ${exp.fairness.identical_conditions ? "" : "bad"}`}>
                      {exp.fairness.identical_conditions ? <ShieldCheck style={{ width: 16, color: "var(--ok)" }} /> : <ShieldAlert style={{ width: 16, color: "var(--crit)" }} />}
                      <div>
                        <div style={{ fontWeight: 500 }}>{exp.fairness.identical_conditions
                          ? "Fair comparison verified — every algorithm faced identical conditions"
                          : "Conditions differed between runs — results are not comparable"}</div>
                        {exp.fairness.repetitions.map((r) => (
                          <div key={r.repetition} className="fp" style={{ marginTop: 3 }}>
                            seed {r.seed} · graph {r.fingerprints.graph?.join("/")} · fleet {r.fingerprints.fleet?.join("/")} · orders {r.fingerprints.orders?.join("/")} · events {r.fingerprints.events?.join("/")}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
                {exp.aggregates && (
                  <div style={{ overflowX: "auto", borderTop: "1px solid var(--line)" }}>
                    <table className="data">
                      <thead><tr><th>Algorithm</th>{COLUMNS.map((c) => <th key={c.key}>{c.label}</th>)}</tr></thead>
                      <tbody>
                        {order.map((a) => (
                          <tr key={a}>
                            <td><i className="swatch" style={{ background: ALGORITHM_COLOR[a] }} />{ALGORITHM_SHORT[a]}</td>
                            {COLUMNS.map((c) => <Cell key={c.key} col={c} stat={exp.aggregates![a]?.[c.key]} isBest={isTop(exp.aggregates![a]?.[c.key]?.mean, best(exp, c))} />)}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <div className="muted" style={{ padding: "8px 12px", fontSize: 11 }}>
                      Highlighted = best in column. Path cost is the planned travel time per route; nodes = search expansions; time = wall-clock search time measured in the worker.
                    </div>
                  </div>
                )}
              </div>

              {exp.aggregates && (
                <>
                  <div className="card">
                    <div className="card-head"><h3>Deliveries over time</h3><p>repetition 1 · simulated time</p></div>
                    <div className="card-body">
                      <LineChart series={deliveriesSeries} height={230} formatX={clock} formatY={(v) => num(v)} yLabel="cumulative deliveries" />
                      {coinciding.length > 0 && (
                        <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>
                          {coinciding.map(([a, b]) => `${ALGORITHM_SHORT[a]} and ${ALGORITHM_SHORT[b]}`).join("; ")} produced identical
                          deliveries at every sample, so their lines coincide.
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="grid g3">
                    {[
                      { key: "avg_route_cost", title: "Path cost", fmt: (v: number) => `${num(v, 0)} s` },
                      { key: "avg_nodes_explored", title: "Nodes explored / search", fmt: (v: number) => num(v, 0) },
                      { key: "avg_planning_ms", title: "Execution time / search", fmt: (v: number) => `${v.toFixed(2)} ms` },
                      { key: "deliveries_completed", title: "Deliveries completed", fmt: (v: number) => num(v, v % 1 ? 1 : 0) },
                      { key: "energy_per_delivery_wh", title: "Energy per delivery", fmt: (v: number) => `${num(v, 0)} Wh` },
                      { key: "replans", title: "Replans", fmt: (v: number) => num(v, v % 1 ? 1 : 0) },
                    ].map((c) => (
                      <div className="card" key={c.key}>
                        <div className="card-head"><h3>{c.title}</h3></div>
                        <div className="card-body">
                          <BarChart format={c.fmt} data={order.map((a) => ({
                            key: a, label: ALGORITHM_SHORT[a], color: ALGORITHM_COLOR[a],
                            value: exp.aggregates![a]?.[c.key]?.mean ?? null, spread: exp.aggregates![a]?.[c.key]?.std ?? null,
                          }))} />
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div></div>
  );
}
