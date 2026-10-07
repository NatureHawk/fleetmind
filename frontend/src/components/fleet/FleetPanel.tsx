import { memo, useEffect, useRef } from "react";
import { useSim } from "../../lib/simulation/store";
import { setFocus } from "../../lib/simulation/stream";
import { STATUS_COLOR } from "../../lib/theme";
import { statusLabel } from "../../lib/formatters";
import { BatteryBar } from "../common/Status";
import type { RobotState, StaticMap } from "../../lib/types";

function describe(r: RobotState, map: StaticMap | null): string {
  if (r.status === "OFFLINE") return "out of service";
  if (!r.target || !map) return r.status === "CHARGING" ? "charging" : "awaiting task";
  const where = map.nodes[r.target.node].name;
  const what = r.target.kind === "CHARGE" ? "charge at" : r.target.kind === "PICKUP" ? "pickup" : "deliver";
  return `${r.current_order && r.target.kind !== "CHARGE" ? r.current_order + " · " : ""}${what} ${where}`;
}

const Row = memo(function Row({ r, selected, flashKey, map }: { r: RobotState; selected: boolean; flashKey: number; map: StaticMap | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!flashKey || !ref.current) return;
    ref.current.classList.remove("flash");
    void ref.current.offsetWidth;
    ref.current.classList.add("flash");
  }, [flashKey]);
  useEffect(() => { if (selected) ref.current?.scrollIntoView({ block: "nearest" }); }, [selected]);
  const color = STATUS_COLOR[r.status];
  return (
    <div ref={ref} className={`robot-row ${selected ? "sel" : ""}`} role="button" tabIndex={0}
         onClick={() => { useSim.getState().select({ type: "robot", id: r.id }); setFocus(r.id); }}
         onMouseEnter={() => useSim.getState().setHoverRobot(r.id)}
         onMouseLeave={() => useSim.getState().setHoverRobot(null)}
         onKeyDown={(e) => { if (e.key === "Enter") { useSim.getState().select({ type: "robot", id: r.id }); setFocus(r.id); } }}>
      <span className="dot" style={{ background: color }} />
      <span className="rid">{r.id}</span>
      <div className="what">
        <div className="st" style={{ color }}>{statusLabel(r.status)}{r.replans > 0 && <span className="muted" style={{ fontWeight: 500, letterSpacing: 0, marginLeft: 6 }}>{r.replans} replan{r.replans > 1 ? "s" : ""}</span>}</div>
        <div className="sub">{describe(r, map)}</div>
      </div>
      <div className="batt">
        <b className="num">{r.battery_pct.toFixed(0)}%</b>
        <BatteryBar pct={r.battery_pct} />
      </div>
    </div>
  );
});

export function FleetPanel() {
  const robots = useSim((s) => s.snapshot?.robots ?? []);
  const selection = useSim((s) => s.selection);
  const flash = useSim((s) => s.replanFlash);
  const map = useSim((s) => s.map);
  const k = useSim((s) => s.snapshot?.kpis);
  const counts = { moving: 0, idle: 0, charging: 0, offline: 0 };
  for (const r of robots) {
    if (r.status === "OFFLINE") counts.offline++;
    else if (r.status === "CHARGING" || (r.status === "WAITING" && r.target?.kind === "CHARGE")) counts.charging++;
    else if (r.status === "IDLE") counts.idle++;
    else counts.moving++;
  }
  return (
    <>
      <div className="fleet-summary">
        <div><b>{counts.moving}</b><span>Active</span></div>
        <div><b>{counts.idle}</b><span>Idle</span></div>
        <div><b>{counts.charging}</b><span>Charging</span></div>
        <div><b style={{ color: counts.offline ? "var(--crit)" : undefined }}>{counts.offline}</b><span>Offline</span></div>
      </div>
      <div className="panel-body">
        {robots.length === 0 && <div className="empty"><strong>Waiting for fleet telemetry</strong>Connecting to the simulation…</div>}
        {robots.map((r) => (
          <Row key={r.id} r={r} map={map} selected={selection?.type === "robot" && selection.id === r.id}
               flashKey={flash.get(r.id) ?? 0} />
        ))}
        {k && <div className="muted" style={{ padding: "10px 12px", fontSize: 11 }}>
          {k.charge_sessions} charging sessions · {k.fleet_messages} fleet messages · {k.preemptions} preemptions
          {k.battery_depletions ? ` · ${k.battery_depletions} depletions` : ""}
        </div>}
      </div>
    </>
  );
}

