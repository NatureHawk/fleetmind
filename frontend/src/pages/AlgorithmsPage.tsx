import { useEffect, useMemo, useRef, useState } from "react";
import { Pause, Play, RotateCcw, Shuffle } from "lucide-react";
import { useSim } from "../lib/simulation/store";
import { api, ApiError } from "../lib/api";
import { buildGeometry, drawBase, fitCamera, toScreen, type Camera, type Geometry } from "../components/simulation/renderer";
import { BarChart } from "../components/analytics/charts";
import { ALGORITHM_COLOR, ALGORITHM_ORDER, ALGORITHM_SHORT } from "../lib/theme";
import { ms, num, pct } from "../lib/formatters";
import type { AlgorithmInfo, AlgorithmKey, TraceResponse, TraceResult } from "../lib/types";

function ExplorerMap({ geo, trace, step, start, goal, onPick }: {
  geo: Geometry; trace: TraceResult | null; step: number; start: number | null; goal: number | null;
  onPick: (node: number) => void;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const camRef = useRef<Camera | null>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });

  useEffect(() => {
    const c = ref.current!;
    const ro = new ResizeObserver(() => {
      const r = c.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      c.width = r.width * dpr;
      c.height = r.height * dpr;
      camRef.current = fitCamera(geo.map, r.width, r.height, 20);
      setSize({ w: r.width, h: r.height });
    });
    ro.observe(c);
    return () => ro.disconnect();
  }, [geo]);

  useEffect(() => {
    const c = ref.current;
    const cam = camRef.current;
    if (!c || !cam || !size.w) return;
    const ctx = c.getContext("2d")!;
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const { w, h } = size;
    const map = geo.map;
    drawBase(ctx, w, h, cam, geo, { blocks: true, labels: false, dimRoads: true });
    if (trace) {
      const color = ALGORITHM_COLOR[trace.algorithm];
      const shown = trace.trace.slice(0, step);
      const expanded = new Set<number>();
      const generated = new Set<number>();
      shown.forEach(([n, added], i) => {
        expanded.add(n);
        added.forEach((a) => generated.add(a));
        const node = map.nodes[n];
        const [x, y] = toScreen(cam, w, h, node.x, node.y);
        ctx.beginPath();
        ctx.arc(x, y, 3.2, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.globalAlpha = 0.25 + 0.6 * ((i + 1) / Math.max(1, shown.length));
        ctx.fill();
      });
      ctx.globalAlpha = 1;
      for (const n of generated) {
        if (expanded.has(n)) continue;
        const node = map.nodes[n];
        const [x, y] = toScreen(cam, w, h, node.x, node.y);
        ctx.beginPath();
        ctx.arc(x, y, 4, 0, Math.PI * 2);
        ctx.strokeStyle = "#e6ebf1";
        ctx.lineWidth = 1.2;
        ctx.stroke();
      }
      if (step > 0 && step <= trace.trace.length) {
        const cur = map.nodes[trace.trace[step - 1][0]];
        const [x, y] = toScreen(cam, w, h, cur.x, cur.y);
        ctx.beginPath();
        ctx.arc(x, y, 7, 0, Math.PI * 2);
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.stroke();
      }
      if (step >= trace.trace.length && trace.path.length > 1) {
        ctx.beginPath();
        trace.path.forEach((id, i) => {
          const n = map.nodes[id];
          const [x, y] = toScreen(cam, w, h, n.x, n.y);
          if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
        });
        ctx.save();
        ctx.shadowColor = color;
        ctx.shadowBlur = 8;
        ctx.strokeStyle = color;
        ctx.lineWidth = 3.5;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.stroke();
        ctx.restore();
      }
    }
    for (const [id, label, fill] of [[start, "START", "#4fd6c4"], [goal, "GOAL", "#e6ebf1"]] as const) {
      if (id == null) continue;
      const n = map.nodes[id];
      const [x, y] = toScreen(cam, w, h, n.x, n.y);
      ctx.beginPath();
      ctx.arc(x, y, 7, 0, Math.PI * 2);
      ctx.fillStyle = "#07090c";
      ctx.fill();
      ctx.lineWidth = 2.5;
      ctx.strokeStyle = fill;
      ctx.stroke();
      ctx.font = "600 10px Inter, sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.lineWidth = 3;
      ctx.strokeStyle = "rgba(7,9,12,0.9)";
      const text = `${label} · ${n.name}`;
      ctx.strokeText(text, x + 11, y);
      ctx.fillStyle = fill;
      ctx.fillText(text, x + 11, y);
    }
  }, [geo, trace, step, start, goal, size]);

  const onClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const cam = camRef.current;
    if (!cam) return;
    const r = e.currentTarget.getBoundingClientRect();
    const sx = e.clientX - r.left, sy = e.clientY - r.top;
    let best: { id: number; d: number } | null = null;
    for (const n of geo.map.nodes) {
      const [x, y] = toScreen(cam, size.w, size.h, n.x, n.y);
      const d = Math.hypot(x - sx, y - sy);
      if (d < 14 && (!best || d < best.d)) best = { id: n.id, d };
    }
    if (best) onPick(best.id);
  };
  return <canvas ref={ref} onClick={onClick} style={{ width: "100%", height: "100%", display: "block", cursor: "crosshair" }}
                 aria-label="Search space visualisation" />;
}

export function AlgorithmsPage() {
  const map = useSim((s) => s.map);
  const toast = useSim((s) => s.toast);
  const geo = useMemo(() => (map ? buildGeometry(map) : null), [map]);
  const [catalog, setCatalog] = useState<AlgorithmInfo[]>([]);
  const [heuristics, setHeuristics] = useState<{ key: string; description: string }[]>([]);
  const [heuristic, setHeuristic] = useState("euclidean");
  const [selected, setSelected] = useState<AlgorithmKey>("astar");
  const [resp, setResp] = useState<TraceResponse | null>(null);
  const [pick, setPick] = useState<{ start: number | null; goal: number | null }>({ start: null, goal: null });
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    const load = () => api.algorithms().then((d) => { setCatalog(d.algorithms); setHeuristics(d.heuristics); }).catch(() => {});
    load();
    const id = window.setInterval(load, 4000);
    return () => window.clearInterval(id);
  }, []);

  const query = async (start?: number, goal?: number, h = heuristic) => {
    try {
      const r = await api.trace({ start, goal, heuristic: h });
      setResp(r);
      setPick({ start: r.start, goal: r.goal });
      setStep(0);
      setPlaying(true);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Trace failed", "error");
    }
  };
  useEffect(() => { if (map && !resp) query(); /* eslint-disable-next-line */ }, [map]);

  const trace = resp?.results.find((r) => r.algorithm === selected) ?? null;
  const total = trace?.trace.length ?? 0;
  useEffect(() => { setStep(0); setPlaying(true); }, [selected]);
  useEffect(() => {
    if (!playing || !trace) return;
    const per = Math.max(1, Math.ceil(total / 220));
    const id = window.setInterval(() => {
      setStep((s) => {
        if (s >= total) { setPlaying(false); return total; }
        return Math.min(total, s + per);
      });
    }, 16);
    return () => window.clearInterval(id);
  }, [playing, trace, total]);

  const onPick = (node: number) => {
    if (pick.start == null || pick.goal != null) {
      setPick({ start: node, goal: null });
      setResp(null);
      setStep(0);
    } else {
      setPick({ start: pick.start, goal: node });
      query(pick.start, node);
    }
  };

  const info = catalog.find((a) => a.key === selected);
  const frontierNow = trace ? (() => {
    const seen = new Set<number>(); const done = new Set<number>();
    trace.trace.slice(0, step).forEach(([n, added]) => { done.add(n); added.forEach((a) => seen.add(a)); });
    let f = 0; for (const s of seen) if (!done.has(s)) f++;
    return f;
  })() : 0;

  return (
    <div className="page"><div className="page-inner">
      <div className="page-head">
        <div>
          <h1>Algorithm explorer</h1>
          <p>Run every search algorithm on the fleet's current world model — live traffic and known closures included — and watch how each explores the road graph. Click the map to choose a start, then a goal.</p>
        </div>
        <div className="actions">
          <label className="inline-field">Heuristic
            <select className="select" value={heuristic} onChange={(e) => { setHeuristic(e.target.value); if (pick.start != null && pick.goal != null) query(pick.start, pick.goal, e.target.value); }}>
              {heuristics.map((h) => <option key={h.key} value={h.key}>{h.key}</option>)}
            </select></label>
          <button className="btn" onClick={() => query()}><Shuffle />Random query</button>
        </div>
      </div>

      <div className="explorer">
        <div className="grid" style={{ alignContent: "start" }}>
          <div className="card">
            <div className="card-head"><h3>Algorithms</h3><p>live stats from the running fleet</p></div>
            <div className="algo-pick" style={{ padding: 6 }}>
              {ALGORITHM_ORDER.map((k) => {
                const a = catalog.find((c) => c.key === k);
                const r = resp?.results.find((x) => x.algorithm === k);
                return (
                  <button key={k} className={selected === k ? "on" : ""} onClick={() => setSelected(k)}>
                    <i style={{ background: ALGORITHM_COLOR[k] }} />
                    <span><span style={{ fontWeight: 500 }}>{a?.name ?? ALGORITHM_SHORT[k]}</span>
                      <span className="muted" style={{ display: "block", fontSize: 11 }}>{a?.family} · {a?.frontier}</span></span>
                    <span className="mono muted" style={{ fontSize: 11 }}>{r ? `${r.nodes_explored} n` : ""}</span>
                  </button>
                );
              })}
            </div>
          </div>
          {info && (
            <div className="card">
              <div className="card-head"><i className="swatch" style={{ background: ALGORITHM_COLOR[info.key], margin: 0 }} /><h3>{info.name}</h3></div>
              <div className="card-body grid" style={{ gap: 10 }}>
                <div><div className="eyebrow" style={{ marginBottom: 3 }}>Purpose</div><div className="dim">{info.purpose}</div></div>
                <div><div className="eyebrow" style={{ marginBottom: 3 }}>In FleetMind</div><div className="dim">{info.fleet_behaviour}</div></div>
                <dl className="kv">
                  <dt>Optimal</dt><dd style={{ fontFamily: "var(--font)", whiteSpace: "normal" }}>{info.optimal}</dd>
                  <dt>Time</dt><dd>{info.time_complexity}</dd>
                  <dt>Space</dt><dd>{info.space_complexity}</dd>
                  <dt>Uses cost / heuristic</dt><dd>{info.uses_cost ? "yes" : "no"} / {info.uses_heuristic ? "yes" : "no"}</dd>
                </dl>
                <div className="muted" style={{ fontSize: 11.5 }}>Good for: {info.performs_well}</div>
                <div style={{ borderTop: "1px solid var(--line)", paddingTop: 10 }}>
                  <div className="eyebrow" style={{ marginBottom: 6 }}>Current simulation</div>
                  {info.live ? (
                    <dl className="kv">
                      <dt>Searches</dt><dd>{info.live.searches}</dd>
                      <dt>Nodes explored (avg)</dt><dd>{num(info.live.avg_nodes_explored, 1)}</dd>
                      <dt>Planning time (avg)</dt><dd>{ms(info.live.avg_planning_ms)}</dd>
                      <dt>Path cost (avg)</dt><dd>{num(info.live.avg_route_cost, 1)} s</dd>
                      <dt>Success rate</dt><dd>{pct(info.live.success_rate, 1)}</dd>
                    </dl>
                  ) : <div className="muted">Not used in the current run. Switch the planner on the Operations map to collect live stats.</div>}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="grid" style={{ alignContent: "start" }}>
          <div className="card" style={{ overflow: "hidden" }}>
            <div className="card-head">
              <h3>Search space</h3>
              <p>{resp ? `${resp.start_name} → ${resp.goal_name} · world model v${resp.world_version}` : pick.start != null ? "Now click a goal" : "Loading…"}</p>
              <div className="right">
                <span className="legend-item"><svg width="12" height="12"><circle cx="6" cy="6" r="3.5" fill={trace ? ALGORITHM_COLOR[trace.algorithm] : "#888"} /></svg>expanded</span>
                <span className="legend-item"><svg width="12" height="12"><circle cx="6" cy="6" r="4" fill="none" stroke="#e6ebf1" /></svg>frontier</span>
              </div>
            </div>
            <div className="explorer-map">{geo && <ExplorerMap geo={geo} trace={trace} step={step} start={pick.start} goal={pick.goal} onPick={onPick} />}</div>
            <div className="scrub">
              <button className="btn icon" onClick={() => { if (step >= total) setStep(0); setPlaying(!playing); }} disabled={!trace}>{playing ? <Pause /> : <Play />}</button>
              <button className="btn icon" onClick={() => { setStep(0); setPlaying(false); }} disabled={!trace}><RotateCcw /></button>
              <input type="range" className="range" min={0} max={total} value={step} onChange={(e) => { setPlaying(false); setStep(Number(e.target.value)); }} />
              <span className="mono muted" style={{ minWidth: 210, textAlign: "right", fontSize: 11.5 }}>
                expanded {Math.min(step, total)} / {total} · frontier {frontierNow}
              </span>
            </div>
          </div>

          {resp && (
            <div className="grid g2">
              <div className="card">
                <div className="card-head"><h3>Same query, every algorithm</h3></div>
                <div style={{ overflowX: "auto" }}>
                  <table className="data">
                    <thead><tr><th>Algorithm</th><th>Nodes</th><th>Frontier peak</th><th>Path cost</th><th>Roads</th><th>Time</th></tr></thead>
                    <tbody>
                      {ALGORITHM_ORDER.map((k) => {
                        const r = resp.results.find((x) => x.algorithm === k)!;
                        const bestCost = Math.min(...resp.results.map((x) => x.cost));
                        return (
                          <tr key={k} onClick={() => setSelected(k)} style={{ cursor: "pointer" }}>
                            <td><i className="swatch" style={{ background: ALGORITHM_COLOR[k] }} />{ALGORITHM_SHORT[k]}</td>
                            <td>{r.nodes_explored}</td>
                            <td>{r.max_frontier}</td>
                            <td className={Math.abs(r.cost - bestCost) < 1e-6 ? "best" : ""}>{r.success ? `${num(r.cost, 1)} s` : "—"}</td>
                            <td>{r.hops}</td>
                            <td>{ms(r.elapsed_ms)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="muted" style={{ padding: "8px 12px", fontSize: 11 }}>Highlighted cost = optimal for this query. Time is measured server-side.</div>
              </div>
              <div className="card">
                <div className="card-head"><h3>Nodes explored</h3><p>this query</p></div>
                <div className="card-body">
                  <BarChart format={(v) => num(v)} data={ALGORITHM_ORDER.map((k) => {
                    const r = resp.results.find((x) => x.algorithm === k)!;
                    return { key: k, label: ALGORITHM_SHORT[k], value: r.nodes_explored, color: ALGORITHM_COLOR[k], highlight: k === selected };
                  })} />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div></div>
  );
}
