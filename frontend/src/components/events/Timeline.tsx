import { useMemo, useState } from "react";
import { useSim, type Selection } from "../../lib/simulation/store";
import { setFocus } from "../../lib/simulation/stream";
import { CATEGORY_COLOR } from "../../lib/theme";
import { clock, titleCase } from "../../lib/formatters";
import type { Category, TimelineEntry } from "../../lib/types";

const GROUPS: { key: string; label: string; cats: Category[] | null }[] = [
  { key: "all", label: "All", cats: null },
  { key: "decisions", label: "Decisions", cats: ["allocation", "replanning", "battery", "coordination", "demo"] },
  { key: "env", label: "World", cats: ["environment", "coordination"] },
  { key: "routes", label: "Routes", cats: ["planning", "replanning"] },
  { key: "orders", label: "Orders", cats: ["order", "allocation"] },
];

function targetOf(e: TimelineEntry): Selection | null {
  if (e.robot_id) return { type: "robot", id: e.robot_id };
  if (e.order_id) return { type: "order", id: e.order_id };
  if (e.road_id != null) return { type: "road", id: e.road_id };
  if (e.node_id != null) return { type: "node", id: e.node_id };
  return null;
}

export function TimelineItem({ e, compact = false }: { e: TimelineEntry; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const target = targetOf(e);
  const reasons: string[] | undefined = e.data?.reasons;
  const searchy = e.kind === "ROUTE_PLANNED" || e.kind === "ROUTE_REPLANNED";
  return (
    <div className={`tl-item sev-${e.severity} kind-${e.category} ${target || reasons ? "clickable" : ""}`}
         onClick={() => {
           if (reasons) setOpen((o) => !o);
           if (target && !compact) {
             useSim.getState().select(target);
             setFocus(target.type === "robot" ? target.id : null);
           }
         }}>
      <div className="tl-time">{clock(e.t)}</div>
      <div style={{ minWidth: 0 }}>
        <div className="tl-kind"><i style={{ background: CATEGORY_COLOR[e.category] }} />{titleCase(e.kind)}</div>
        <div className="tl-msg">{e.message}</div>
        {reasons && (open || compact) && (
          <div className="tl-detail">
            <div className="eyebrow" style={{ marginBottom: 5 }}>Why {e.data.robot_id}?</div>
            <ul>{reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            {e.data.runner_up && <div className="muted" style={{ marginTop: 6 }}>
              Runner-up <span className="mono">{e.data.runner_up.robot_id}</span> scored <span className="mono">{e.data.runner_up.score}</span> vs <span className="mono">{e.data.score}</span>
            </div>}
          </div>
        )}
        {reasons && !open && !compact && <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>Show reasoning ▸</div>}
        {searchy && e.data?.path && compact && (
          <div className="muted mono" style={{ fontSize: 10.5, marginTop: 3 }}>
            {e.data.nodes_generated} generated · frontier peak {e.data.max_frontier} · {e.data.energy_pct}% battery
          </div>
        )}
      </div>
    </div>
  );
}

export function Timeline() {
  const events = useSim((s) => s.events);
  const [group, setGroup] = useState("decisions");
  const [paused, setPaused] = useState(false);
  const [frozen, setFrozen] = useState<TimelineEntry[] | null>(null);
  const cats = GROUPS.find((g) => g.key === group)!.cats;
  const source = paused && frozen ? frozen : events;
  const list = useMemo(() => {
    const filtered = cats ? source.filter((e) => cats.includes(e.category)) : source;
    return filtered.slice(-250).reverse();
  }, [source, cats]);
  return (
    <>
      <div className="filter-row" style={{ alignItems: "center", flexWrap: "nowrap" }}>
        {GROUPS.map((g) => (
          <button key={g.key} className={`pill ${group === g.key ? "on" : ""}`} onClick={() => setGroup(g.key)}>{g.label}</button>
        ))}
        <button className={`pill ${paused ? "on" : ""}`} style={{ marginLeft: "auto" }}
                onClick={() => { setPaused(!paused); setFrozen(paused ? null : events); }}
                title="Freeze the feed to read it">{paused ? "Frozen" : "Live"}</button>
      </div>
      <div className="panel-body" aria-live="polite">
        {list.length === 0 && <div className="empty"><strong>No events yet</strong>Start the simulation to see the fleet's decisions.</div>}
        {list.map((e) => <TimelineItem key={e.seq} e={e} />)}
      </div>
    </>
  );
}

