import { useState } from "react";
import { ChevronDown, Layers as LayersIcon } from "lucide-react";
import { useSim, type Layers } from "../../lib/simulation/store";
import { STATUS_COLOR, TRAFFIC_COLOR } from "../../lib/theme";

const ROWS: { key: keyof Layers; label: string }[] = [
  { key: "routes", label: "All routes" },
  { key: "traffic", label: "Traffic" },
  { key: "labels", label: "Labels" },
  { key: "blocks", label: "City blocks" },
];

export function LayersPanel() {
  const layers = useSim((s) => s.layers);
  const toggle = useSim((s) => s.toggleLayer);
  const [open, setOpen] = useState(() => {
    try { return localStorage.getItem("fm.legend") === "open"; } catch { return false; }
  });
  const flip = () => {
    setOpen(!open);
    try { localStorage.setItem("fm.legend", open ? "closed" : "open"); } catch { /* storage unavailable */ }
  };
  if (!open) {
    return (
      <button className="overlay glass btn" style={{ top: 12, right: 12, height: 32 }} onClick={flip} aria-expanded={false}>
        <LayersIcon />Layers & legend<ChevronDown style={{ width: 12 }} />
      </button>
    );
  }
  return (
    <div className="overlay glass layers">
      <div className="row" onClick={flip} style={{ marginBottom: 2 }} role="button" aria-expanded>
        <span className="eyebrow">Layers</span><ChevronDown style={{ width: 13, transform: "rotate(180deg)" }} />
      </div>
      {ROWS.map((r) => (
        <div key={r.key} className="row" onClick={() => toggle(r.key)} role="switch" aria-checked={layers[r.key]}
             tabIndex={0} onKeyDown={(e) => e.key === "Enter" && toggle(r.key)}>
          <span>{r.label}</span>
          <span className={`toggle ${layers[r.key] ? "on" : ""}`} />
        </div>
      ))}
      <div className="legend">
        <div className="legend-item">
          <svg width="14" height="14"><rect x="2" y="2" width="10" height="10" fill="#1a1710" stroke="#d7a23a" strokeWidth="1.4" /></svg>Warehouse
        </div>
        <div className="legend-item">
          <svg width="14" height="14"><rect x="2" y="2" width="10" height="10" rx="2" fill="#0e1a14" stroke="#5ec27a" strokeWidth="1.4" /></svg>Charging station
        </div>
        <div className="legend-item">
          <svg width="14" height="14"><circle cx="7" cy="7" r="2.6" fill="#c9d6e6" /><circle cx="7" cy="7" r="5.5" fill="none" stroke="#8fb8ff" strokeWidth="1.2" /></svg>Customer · order inbound
        </div>
        <div className="legend-item">
          <svg width="14" height="14"><circle cx="7" cy="7" r="4.5" fill="#0a0d11" stroke={STATUS_COLOR.EN_ROUTE} strokeWidth="2" /></svg>Robot · ring = battery
        </div>
        <div className="legend-item">
          <svg width="14" height="14"><line x1="1" y1="7" x2="13" y2="7" stroke={TRAFFIC_COLOR.jammed} strokeWidth="2.5" /></svg>Congested road
        </div>
        <div className="legend-item">
          <svg width="14" height="14"><line x1="1" y1="7" x2="13" y2="7" stroke="#ef5a5a" strokeWidth="2.5" strokeDasharray="3 2" /></svg>Closed road
        </div>
        <div className="legend-item">
          <svg width="14" height="14"><line x1="1" y1="7" x2="13" y2="7" stroke="rgba(239,90,90,0.5)" strokeWidth="2.5" strokeDasharray="1.5 2.5" /></svg>Closure not yet detected
        </div>
        <div className="legend-item">
          <svg width="14" height="14"><line x1="1" y1="7" x2="13" y2="7" stroke="#ef5a5a" strokeWidth="1.6" strokeDasharray="3 2.5" /></svg>Invalidated route
        </div>
      </div>
    </div>
  );
}
