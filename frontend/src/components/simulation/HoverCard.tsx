import { useSim } from "../../lib/simulation/store";
import { STATUS_COLOR, TRAFFIC_COLOR } from "../../lib/theme";
import { num, statusLabel, titleCase } from "../../lib/formatters";
import type { HoverTarget } from "./renderer";

export function HoverCard({ target, x, y }: { target: HoverTarget; x: number; y: number }) {
  const map = useSim((s) => s.map);
  const snapshot = useSim((s) => s.snapshot);
  const roads = useSim((s) => s.roads);
  const tool = useSim((s) => s.tool);
  if (!map) return null;

  let body: JSX.Element | null = null;
  if (target.type === "robot") {
    const r = snapshot?.robots.find((x) => x.id === target.id);
    if (!r) return null;
    body = (
      <>
        <div className="title"><span className="mono">{r.id}</span>
          <span style={{ color: STATUS_COLOR[r.status], fontSize: 10, letterSpacing: "0.07em" }}>{statusLabel(r.status)}</span></div>
        <div className="line">Battery <span className="mono">{r.battery_pct.toFixed(0)}%</span></div>
        <div className="line">Task <span className="mono">{r.current_order ?? "—"}</span></div>
        {r.target && <div className="line">Heading to <span className="mono">{titleCase(r.target.kind)} {map.nodes[r.target.node].name}</span></div>}
      </>
    );
  } else if (target.type === "node") {
    const n = map.nodes[target.id];
    const cs = snapshot?.chargers.find((c) => c.node === n.id);
    body = (
      <>
        <div className="title"><span className="mono">{n.name}</span><span className="muted">{titleCase(n.kind)}</span></div>
        <div className="line">Zone <span>{titleCase(n.zone)}</span></div>
        {cs && <div className="line">Occupancy <span className="mono">{cs.charging.length}/{cs.slots}{cs.queue.length ? ` · ${cs.queue.length} queued` : ""}</span></div>}
        {cs && !cs.available && <div className="line" style={{ color: "var(--crit)" }}>Unavailable</div>}
      </>
    );
  } else {
    const road = map.roads[target.id];
    const st = roads.get(road.id);
    const traffic = st?.traffic ?? "low";
    body = (
      <>
        <div className="title"><span className="mono">{road.name}</span><span className="muted">{titleCase(road.class)}</span></div>
        <div className="line">Length <span className="mono">{num(road.length)} m</span></div>
        <div className="line">Traffic <span style={{ color: traffic === "low" ? "var(--text-0)" : TRAFFIC_COLOR[traffic] }}>{titleCase(traffic)}</span></div>
        {st?.blocked && <div className="line" style={{ color: "var(--crit)" }}>{st.known ? "Closed" : "Closed — not yet detected"}</div>}
        {tool && <div className="line" style={{ color: tool === "block" ? "var(--crit)" : "var(--serious)", marginTop: 3 }}>
          Click to {tool === "block" ? "close this road" : "add congestion"}</div>}
      </>
    );
  }
  return <div className="hovercard" style={{ left: x, top: y }}>{body}</div>;
}
