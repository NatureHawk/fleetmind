import { useState } from "react";
import { useSim } from "../../lib/simulation/store";
import { setFocus } from "../../lib/simulation/stream";
import { PRIORITY_COLOR } from "../../lib/theme";
import { duration, statusLabel } from "../../lib/formatters";
import type { OrderState } from "../../lib/types";

type Filter = "open" | "pending" | "done";

export function OrdersPanel() {
  const snapshot = useSim((s) => s.snapshot);
  const map = useSim((s) => s.map);
  const selection = useSim((s) => s.selection);
  const [filter, setFilter] = useState<Filter>("open");
  if (!snapshot || !map) return <div className="empty">No data yet</div>;
  const t = snapshot.t;
  const open = snapshot.orders;
  let rows: OrderState[] = filter === "open" ? open : filter === "pending" ? open.filter((o) => o.status === "PENDING")
    : snapshot.recent_orders;
  rows = [...rows].sort((a, b) => filter === "done" ? 0 : (prioRank(b) - prioRank(a)) || a.deadline - b.deadline);

  const onClick = (o: OrderState) => {
    useSim.getState().select({ type: "order", id: o.id });
    if (o.assigned_robot) setFocus(o.assigned_robot);
  };
  return (
    <>
      <div className="filter-row">
        {(["open", "pending", "done"] as Filter[]).map((f) => (
          <button key={f} className={`pill ${filter === f ? "on" : ""}`} onClick={() => setFilter(f)}>
            {f === "open" ? `Open ${open.length}` : f === "pending" ? `Unassigned ${open.filter((o) => o.status === "PENDING").length}` : "Recently closed"}
          </button>
        ))}
      </div>
      <div className="panel-body">
        {rows.length === 0 && <div className="empty"><strong>No orders here</strong>{filter === "pending" ? "Every open order has a robot." : "Orders appear as requests arrive."}</div>}
        {rows.map((o) => {
          const left = o.deadline - t;
          const sel = selection?.type === "order" && selection.id === o.id;
          return (
            <div key={o.id} className={`order-row ${sel ? "sel" : ""}`} onClick={() => onClick(o)} role="button" tabIndex={0}>
              <div>
                <div className="oid"><span className="prio" style={{ background: PRIORITY_COLOR[o.priority] }} />{o.id}</div>
                <div className="meta">{o.priority}</div>
              </div>
              <div style={{ minWidth: 0 }}>
                <div className="route">{map.nodes[o.source].name} → {map.nodes[o.destination].name}</div>
                <div className="meta">{statusLabel(o.status)}{o.assigned_robot ? ` · ${o.assigned_robot}` : ""}</div>
              </div>
              <div style={{ textAlign: "right" }}>
                {o.status === "DELIVERED" ? (
                  <span className="mono" style={{ fontSize: 11, color: o.late ? "var(--warn)" : "var(--ok)" }}>{o.late ? "late" : "on time"}</span>
                ) : o.status === "FAILED" || o.status === "CANCELLED" ? (
                  <span className="mono" style={{ fontSize: 11, color: "var(--crit)" }}>{o.status.toLowerCase()}</span>
                ) : (
                  <span className="mono" style={{ fontSize: 11, color: left < 0 ? "var(--crit)" : left < 180 ? "var(--warn)" : "var(--text-1)" }}>
                    {left < 0 ? `-${duration(-left)}` : duration(left)}
                  </span>
                )}
                <div className="meta">{o.status === "DELIVERED" || o.status === "FAILED" || o.status === "CANCELLED" ? "" : "to deadline"}</div>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

function prioRank(o: OrderState) {
  return { LOW: 0, NORMAL: 1, HIGH: 2, CRITICAL: 3 }[o.priority];
}
