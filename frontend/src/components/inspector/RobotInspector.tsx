import { Brain, Eye, Footprints, RefreshCw, X } from "lucide-react";
import { useSim } from "../../lib/simulation/store";
import { setFocus } from "../../lib/simulation/stream";
import { usePoll } from "../../hooks/usePoll";
import { api } from "../../lib/api";
import { BatteryBar, StatusBadge } from "../common/Status";
import { clock, duration, ms, num, pct, titleCase } from "../../lib/formatters";
import { ALGORITHM_COLOR } from "../../lib/theme";
import type { RobotDetail } from "../../lib/types";

const PHASE_COLOR: Record<string, string> = {
  PERCEIVE: "#8fb8ff", DECIDE: "#4fd6c4", ACT: "#a9b4c2", REPLAN: "#f2b544", BATTERY: "#5ec27a",
};

export function RobotInspector({ id, onClose }: { id: string; onClose: () => void }) {
  const live = useSim((s) => (s.focus?.id === id ? s.focus : null));
  // Fallback fetch (e.g. before the first focused snapshot arrives or while paused).
  const { data } = usePoll(() => api.robot(id), [id], live ? 0 : 2000);
  const r: RobotDetail | null = live ?? data;
  if (!r) return <div className="empty">Loading {id}…</div>;
  const loop = r.loop;
  const active = (k: string) => loop.phase === k || (loop.phase === "ACT" && k === "ACT");
  const used = r.orders.length;
  return (
    <>
      <div className="insp-head">
        <div className="insp-title">
          <h2>{r.id}</h2>
          <div>
            <StatusBadge status={r.status} />
            <div className="sub" style={{ marginTop: 3 }}>{r.model} · since {clock(r.status_since)}</div>
          </div>
          <button className="btn ghost sm icon close" onClick={onClose} aria-label="Close inspector"><X /></button>
        </div>
        <div style={{ marginTop: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
            <span className="muted">Battery</span>
            <span className="mono">{r.battery_pct.toFixed(1)}% <span className="muted">· {num(r.battery_wh)} / {num(r.max_battery_wh)} Wh</span></span>
          </div>
          <BatteryBar pct={r.battery_pct} />
          {r.plan && r.route.length > 0 && (
            <div className="muted" style={{ fontSize: 11, marginTop: 5 }}>
              Remaining route needs ≈{r.remaining_energy_pct.toFixed(0)}% {r.low_battery && <span style={{ color: "var(--warn)" }}>· low-battery mode</span>}
            </div>
          )}
        </div>
      </div>

      <div className="stat-grid">
        <div><div className="k">Current order</div><div className="v">{r.current_order ?? "—"}</div></div>
        <div><div className="k">Destination</div><div className="v">{r.plan?.goal_name ?? (r.stops[0]?.name ?? "—")}</div></div>
        <div><div className="k">Load</div><div className="v">{r.carrying.length}<small>on board · {used}/{r.capacity}</small></div></div>
        <div>
          <div className="k">Algorithm</div>
          <div className="v" style={{ display: "flex", alignItems: "center", gap: 6 }}>
            {r.plan && <i className="swatch" style={{ background: ALGORITHM_COLOR[r.plan.algorithm], margin: 0 }} />}
            {r.plan?.algorithm_name ?? "—"}
          </div>
        </div>
        <div><div className="k">Route cost</div><div className="v">{r.plan ? num(r.plan.cost, 1) : "—"}<small>s</small></div></div>
        <div><div className="k">Nodes explored</div><div className="v">{r.plan ? num(r.plan.nodes_explored) : "—"}</div></div>
        <div><div className="k">Plan time</div><div className="v">{r.plan ? ms(r.plan.elapsed_ms) : "—"}</div></div>
        <div><div className="k">Distance</div><div className="v">{r.distance_km.toFixed(2)}<small>km</small></div></div>
        <div><div className="k">Energy used</div><div className="v">{num(r.energy_wh)}<small>Wh · {r.energy_pct_used.toFixed(0)}%</small></div></div>
        <div><div className="k">Replans</div><div className="v">{r.replans}</div></div>
        <div><div className="k">Delivered</div><div className="v">{r.orders_completed}</div></div>
        <div><div className="k">Utilisation</div><div className="v">{pct(r.stats.utilization)}</div></div>
      </div>

      <div className="panel-body">
        <div className="section">
          <div className="section-title"><span className="eyebrow">Agent loop</span><span className="muted mono" style={{ fontSize: 10.5 }}>{r.speed_mps.toFixed(1)} m/s · {r.speed_factor.toFixed(2)}×</span></div>
          <div className="loop">
            {[
              { k: "PERCEIVE", icon: <Eye />, on: true },
              { k: "DECIDE", icon: <Brain />, on: loop.phase === "DECIDE" || loop.phase === "ACT" },
              { k: "ACT", icon: <Footprints />, on: active("ACT") },
              { k: "REPLAN", icon: <RefreshCw />, on: loop.phase === "REPLAN" },
            ].map((s) => (
              <div key={s.k} className={`loop-step ${s.k === "REPLAN" ? "replan" : ""} ${s.on ? "on" : ""}`}>
                <div className="h">{s.icon}{s.k}{s.on && s.k !== "REPLAN" && <span style={{ marginLeft: "auto" }}>✓</span>}</div>
              </div>
            ))}
          </div>
          <div className="loop-text">
            <div><span>PERCEIVE</span><span>{loop.perceive}</span></div>
            <div><span>DECIDE</span><span>{loop.decide}</span></div>
            <div><span>ACT</span><span>{loop.act}</span></div>
          </div>
        </div>

        {r.plan && (
          <div className="section">
            <div className="section-title"><span className="eyebrow">Active plan</span>
              <span className="muted mono" style={{ fontSize: 10.5 }}>{titleCase(r.plan.trigger === "PLAN" ? r.plan.purpose : `replan · ${r.plan.trigger}`)}</span></div>
            <dl className="kv">
              <dt>Search</dt><dd>{r.plan.algorithm_name} · {r.plan.nodes_explored} expanded · {r.plan.nodes_generated} generated</dd>
              <dt>Route</dt><dd>{r.plan.hops} roads · {num(r.plan.cost, 1)} s</dd>
              <dt>Energy estimate</dt><dd>{num(r.plan.energy_wh, 1)} Wh</dd>
              <dt>Planned at</dt><dd>{clock(r.plan.planned_at)}{r.plan.cached ? " · cached" : ""}</dd>
            </dl>
            {r.route_names.length > 0 && (
              <div className="mono muted" style={{ fontSize: 10.5, marginTop: 8, lineHeight: 1.6, wordBreak: "break-word" }}>
                {r.route_names.slice(0, 14).join(" → ")}{r.route_names.length > 14 ? ` → … (${r.route_names.length - 14} more)` : ""}
              </div>
            )}
          </div>
        )}

        <div className="section">
          <div className="section-title"><span className="eyebrow">Task queue</span><span className="muted">{r.stops.length} stop{r.stops.length === 1 ? "" : "s"}</span></div>
          {r.stops.length === 0 ? <div className="muted">No tasks — {r.status === "IDLE" ? "available for assignment" : titleCase(r.status)}</div> : (
            <div className="stops">
              {r.stops.map((s, i) => (
                <div key={i} className={`stop ${i === 0 ? "cur" : ""}`}>
                  <span className="n">{i + 1}</span>
                  <span className="eyebrow" style={{ fontSize: 9.5 }}>{s.kind}</span>
                  <span className="mono">{s.name}</span>
                  <span className="muted mono" style={{ fontSize: 11 }}>{s.order_id ?? ""}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="section">
          <div className="section-title"><span className="eyebrow">Decision log</span><span className="muted">{duration(r.stats.busy_time)} busy · {duration(r.stats.idle_time)} idle</span></div>
          {r.decisions.length === 0 && <div className="muted">No decisions yet.</div>}
          {[...r.decisions].reverse().map((d, i) => (
            <div key={i} className="decision">
              <span className="t">{clock(d.t)}</span>
              <span className="p" style={{ color: PHASE_COLOR[d.phase] ?? "var(--text-2)" }}>{d.phase}</span>
              <span className="m">{d.message}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

export function closeSelection() {
  useSim.getState().select(null);
  setFocus(null);
}
