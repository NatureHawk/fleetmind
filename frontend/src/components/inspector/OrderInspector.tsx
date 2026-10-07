import { X } from "lucide-react";
import { usePoll } from "../../hooks/usePoll";
import { api } from "../../lib/api";
import { useSim } from "../../lib/simulation/store";
import { setFocus } from "../../lib/simulation/stream";
import { PriorityTag } from "../common/Status";
import { clock, duration, statusLabel } from "../../lib/formatters";

const COMPONENT_COLOR: Record<string, string> = {
  travel: "#3987e5", workload: "#d95926", battery: "#199e70", deadline: "#c98500",
};
const COMPONENT_LABEL: Record<string, string> = {
  travel: "Travel", workload: "Workload", battery: "Battery", deadline: "Deadline",
};

export function OrderInspector({ id, onClose }: { id: string; onClose: () => void }) {
  const { data: o, error } = usePoll(() => api.order(id), [id], 1500);
  if (error && !o) return <div className="empty"><strong>Order unavailable</strong>{error}</div>;
  if (!o) return <div className="empty">Loading {id}…</div>;
  const ex = o.explanation;
  const maxScore = ex ? Math.max(ex.score, ...(ex.candidates.map((c) => c.score ?? 0))) || 1 : 1;
  const pickRobot = (rid: string) => { useSim.getState().select({ type: "robot", id: rid }); setFocus(rid); };
  return (
    <>
      <div className="insp-head">
        <div className="insp-title">
          <h2>{o.id}</h2>
          <div><PriorityTag priority={o.priority} /><div className="sub" style={{ marginTop: 3 }}>{statusLabel(o.status)}</div></div>
          <button className="btn ghost sm icon close" onClick={onClose} aria-label="Close inspector"><X /></button>
        </div>
      </div>
      <div className="stat-grid">
        <div><div className="k">Pickup</div><div className="v">{o.source_name}</div></div>
        <div><div className="k">Drop-off</div><div className="v">{o.destination_name}</div></div>
        <div><div className="k">Robot</div><div className="v">{o.assigned_robot ?? "—"}</div></div>
        <div><div className="k">Created</div><div className="v">{clock(o.created_at)}</div></div>
        <div><div className="k">Deadline</div><div className="v">{clock(o.deadline)}</div></div>
        <div><div className="k">{o.delivery_time != null ? "Delivered in" : "Time left"}</div>
          <div className="v" style={{ color: o.time_to_deadline != null && o.time_to_deadline < 0 ? "var(--crit)" : undefined }}>
            {o.delivery_time != null ? duration(o.delivery_time) : o.time_to_deadline != null ? (o.time_to_deadline < 0 ? "overdue" : duration(o.time_to_deadline)) : "—"}
          </div></div>
      </div>
      <div className="panel-body">
        {o.failure_reason && <div className="section" style={{ color: "var(--crit)" }}>{o.failure_reason}</div>}
        <div className="section">
          <div className="section-title"><span className="eyebrow">Assignment reasoning</span>
            {ex && <span className="muted mono" style={{ fontSize: 10.5 }}>at {clock(ex.t)}</span>}</div>
          {!ex ? <div className="muted">Not assigned yet — the allocator re-scores the fleet every 2 s.</div> : (
            <>
              <div style={{ marginBottom: 10 }}>
                Assigned to <button className="btn sm" onClick={() => pickRobot(ex.robot_id)} style={{ margin: "0 4px" }}>{ex.robot_id}</button>
                with score <span className="mono">{ex.score}</span>
                {ex.preempted_order && <span style={{ color: "var(--warn)" }}> · preempted {ex.preempted_order}</span>}
              </div>
              <div className="tl-detail" style={{ margin: "0 0 12px" }}>
                <ul>{ex.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
              </div>
              <div className="eyebrow" style={{ marginBottom: 7 }}>Score breakdown (seconds, lower wins)</div>
              <div className="score-bars">
                {Object.entries(ex.components).map(([k, v]) => (
                  <div className="score-row" key={k}>
                    <span className="muted"><i className="swatch" style={{ background: COMPONENT_COLOR[k] }} />{COMPONENT_LABEL[k] ?? k}</span>
                    <div className="track"><span style={{ width: `${(v / maxScore) * 100}%`, background: COMPONENT_COLOR[k] }} /></div>
                    <span className="mono" style={{ textAlign: "right" }}>{v.toFixed(0)}</span>
                  </div>
                ))}
              </div>
              <div className="eyebrow" style={{ margin: "14px 0 4px" }}>Candidates ({ex.eligible_count} eligible)</div>
              <div className="cand muted" style={{ fontSize: 10.5 }}>
                <span>Robot</span><span>Score composition</span><span style={{ textAlign: "right" }}>Pickup</span><span style={{ textAlign: "right" }}>Batt.</span>
              </div>
              {ex.candidates.map((c) => (
                <div key={c.robot_id} className={`cand ${c.robot_id === ex.robot_id ? "win" : ""}`}>
                  <button className="btn ghost sm" style={{ padding: 0, height: 20, justifyContent: "flex-start" }}
                          onClick={() => pickRobot(c.robot_id)}><span className="mono">{c.robot_id}</span></button>
                  <div className="track" style={{ display: "flex", height: 6, borderRadius: 3, overflow: "hidden", background: "rgba(148,163,184,0.1)", gap: 2 }}>
                    {Object.entries(c.components).map(([k, v]) => v > 0 && (
                      <span key={k} title={`${COMPONENT_LABEL[k]} ${v.toFixed(0)}`}
                            style={{ width: `${(v / maxScore) * 100}%`, background: COMPONENT_COLOR[k] }} />
                    ))}
                  </div>
                  <span className="mono" style={{ textAlign: "right" }}>{duration(c.pickup_eta)}</span>
                  <span className="mono" style={{ textAlign: "right" }}>{c.battery_after_pct.toFixed(0)}%</span>
                </div>
              ))}
              {ex.rejected.length > 0 && (
                <div className="muted" style={{ marginTop: 10, fontSize: 11.5 }}>
                  Ineligible: {ex.rejected.map((r) => `${r.count} ${r.reason}`).join(" · ")}
                </div>
              )}
            </>
          )}
        </div>
        <div className="section">
          <div className="section-title"><span className="eyebrow">History</span></div>
          {o.history.map((h, i) => (
            <div key={i} className="decision" style={{ gridTemplateColumns: "56px 1fr" }}>
              <span className="t">{clock(h.t)}</span><span className="m">{h.message}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
