import { Construction, PlugZap, TrafficCone, X } from "lucide-react";
import { usePoll } from "../../hooks/usePoll";
import { useCommands } from "../../hooks/useCommands";
import { api } from "../../lib/api";
import { useSim } from "../../lib/simulation/store";
import { setFocus } from "../../lib/simulation/stream";
import { TRAFFIC_COLOR } from "../../lib/theme";
import { clock, num, titleCase } from "../../lib/formatters";

function RobotLinks({ ids }: { ids: string[] }) {
  if (!ids.length) return <span className="muted">none</span>;
  return (
    <span style={{ display: "inline-flex", gap: 4, flexWrap: "wrap", justifyContent: "flex-end" }}>
      {ids.map((id) => (
        <button key={id} className="btn sm" style={{ height: 20, padding: "0 6px" }}
                onClick={() => { useSim.getState().select({ type: "robot", id }); setFocus(id); }}>
          <span className="mono">{id}</span>
        </button>
      ))}
    </span>
  );
}

export function RoadInspector({ id, onClose }: { id: number; onClose: () => void }) {
  const { data: r, setData } = usePoll(() => api.road(id), [id], 1500);
  const cmd = useCommands();
  if (!r) return <div className="empty">Loading road…</div>;
  const refresh = async () => setData(await api.road(id));
  const traffic = (lvl: string) => lvl === "low" ? "var(--text-0)" : TRAFFIC_COLOR[lvl as keyof typeof TRAFFIC_COLOR];
  return (
    <>
      <div className="insp-head">
        <div className="insp-title">
          <h2>{r.name}</h2>
          <div><span className="badge soft" style={{ color: r.blocked ? "var(--crit)" : "var(--ok)" }}><i />{r.blocked ? "Closed" : "Open"}</span>
            <div className="sub" style={{ marginTop: 3 }}>{titleCase(r.road_class)} road · {r.source_name} ↔ {r.destination_name}</div></div>
          <button className="btn ghost sm icon close" onClick={onClose} aria-label="Close inspector"><X /></button>
        </div>
      </div>
      <div className="stat-grid">
        <div><div className="k">Road ID</div><div className="v">E-{r.id}</div></div>
        <div><div className="k">Distance</div><div className="v">{num(r.distance)}<small>m</small></div></div>
        <div><div className="k">Traffic</div><div className="v" style={{ color: traffic(r.traffic_level) }}>{titleCase(r.traffic_level)}</div></div>
        <div><div className="k">Travel time</div><div className="v">{num(r.travel_time, 1)}<small>s</small></div></div>
        <div><div className="k">Energy cost</div><div className="v">{num(r.energy_cost, 1)}<small>Wh</small></div></div>
        <div><div className="k">Speed factor</div><div className="v">{r.speed_factor}×</div></div>
      </div>
      <div className="panel-body">
        <div className="section">
          <div className="section-title"><span className="eyebrow">Ground truth vs fleet knowledge</span></div>
          <dl className="kv">
            <dt>Status</dt><dd style={{ color: r.blocked ? "var(--crit)" : undefined }}>{r.blocked ? "closed" : "open"}</dd>
            <dt>Known to fleet as</dt><dd style={{ color: r.blocked_known_to_fleet ? "var(--crit)" : r.blocked ? "var(--warn)" : undefined }}>
              {r.blocked_known_to_fleet ? "closed" : r.blocked ? "open — not yet detected" : "open"}</dd>
            <dt>Known traffic</dt><dd>{r.known_traffic_level}</dd>
            <dt>Planner edge cost</dt><dd>{num(r.planner_cost, 1)} s</dd>
            <dt>Robots routed here</dt><dd><RobotLinks ids={r.robots_routed} /></dd>
          </dl>
          {r.blocked && !r.blocked_known_to_fleet && (
            <p className="muted" style={{ margin: "10px 0 0", fontSize: 11.5 }}>
              Robots plan on the shared world model. This closure is invisible to planners until a robot perceives it from an adjacent junction and reports it.
            </p>
          )}
        </div>
        <div className="section" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {r.blocked ? (
            <button className="btn" onClick={async () => { await cmd.inject({ type: "ROAD_REOPENED", road_id: r.id }, `${r.name} reopened`); refresh(); }}>
              <Construction />Reopen road</button>
          ) : (
            <button className="btn danger" onClick={async () => { await cmd.inject({ type: "ROAD_BLOCKED", road_id: r.id }, `${r.name} closed`); refresh(); }}>
              <Construction />Close road</button>
          )}
          {r.traffic_level === "low" ? (
            <button className="btn" onClick={async () => { await cmd.inject({ type: "TRAFFIC_INCREASE", road_ids: [r.id], level: "JAMMED" }, `Traffic jammed on ${r.name}`); refresh(); }}>
              <TrafficCone />Add congestion</button>
          ) : (
            <button className="btn" onClick={async () => { await cmd.inject({ type: "TRAFFIC_CLEAR", road_ids: [r.id] }, `Traffic cleared on ${r.name}`); refresh(); }}>
              <TrafficCone />Clear traffic</button>
          )}
        </div>
      </div>
    </>
  );
}

export function NodeInspector({ id, onClose }: { id: number; onClose: () => void }) {
  const { data: n, setData } = usePoll(() => api.node(id), [id], 1500);
  const cmd = useCommands();
  if (!n) return <div className="empty">Loading…</div>;
  const st = n.station;
  return (
    <>
      <div className="insp-head">
        <div className="insp-title">
          <h2>{n.name}</h2>
          <div><span className="badge soft" style={{ color: "var(--text-1)" }}>{titleCase(n.kind)}</span>
            <div className="sub" style={{ marginTop: 3 }}>{titleCase(n.zone)} zone · {n.degree} roads</div></div>
          <button className="btn ghost sm icon close" onClick={onClose} aria-label="Close inspector"><X /></button>
        </div>
      </div>
      {st && (
        <div className="stat-grid">
          <div><div className="k">Occupancy</div><div className="v">{st.occupancy}<small>/ {st.slots}</small></div></div>
          <div><div className="k">Queue</div><div className="v">{st.queue.length}</div></div>
          <div><div className="k">Available</div><div className="v" style={{ color: st.available ? undefined : "var(--crit)" }}>
            {st.available ? st.available_capacity : "closed"}</div></div>
          <div><div className="k">Inbound</div><div className="v">{st.inbound.length}</div></div>
          <div><div className="k">Sessions</div><div className="v">{st.sessions}</div></div>
          <div><div className="k">Delivered</div><div className="v">{num(st.energy_delivered_wh / 1000, 2)}<small>kWh</small></div></div>
        </div>
      )}
      <div className="panel-body">
        {st && (
          <div className="section">
            <dl className="kv">
              <dt>Charging</dt><dd><RobotLinks ids={st.charging} /></dd>
              <dt>Queue (FIFO)</dt><dd><RobotLinks ids={st.queue} /></dd>
              <dt>Reserved / en route</dt><dd><RobotLinks ids={st.inbound} /></dd>
              {!st.available && st.unavailable_until != null && <><dt>Unavailable until</dt><dd>{clock(st.unavailable_until)}</dd></>}
            </dl>
            <div style={{ marginTop: 12 }}>
              <button className="btn" disabled={!st.available}
                      onClick={async () => { await cmd.inject({ type: "CHARGING_STATION_BUSY", node_id: n.id, duration_s: 300 }, `${n.name} unavailable for 5 min`); setData(await api.node(id)); }}>
                <PlugZap />Make unavailable (5 min)</button>
            </div>
          </div>
        )}
        {n.orders_waiting && (
          <div className="section"><div className="section-title"><span className="eyebrow">Orders awaiting pickup</span><span className="muted">{n.orders_waiting.length}</span></div>
            <div className="mono dim" style={{ lineHeight: 1.8 }}>{n.orders_waiting.join("  ") || <span className="muted">none</span>}</div></div>
        )}
        {n.orders_inbound && (
          <div className="section"><div className="section-title"><span className="eyebrow">Inbound deliveries</span><span className="muted">{n.orders_inbound.length}</span></div>
            <div className="mono dim" style={{ lineHeight: 1.8 }}>{n.orders_inbound.join("  ") || <span className="muted">none</span>}</div></div>
        )}
        <div className="section">
          <div className="section-title"><span className="eyebrow">Connected roads</span></div>
          {n.roads.map((r) => (
            <div key={r.id} className="decision" style={{ gridTemplateColumns: "60px 1fr", cursor: "pointer" }}
                 onClick={() => useSim.getState().select({ type: "road", id: r.id })}>
              <span className="mono">{r.name}</span><span className="m">to {r.to}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
