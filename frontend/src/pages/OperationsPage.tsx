import { useCallback, useEffect, useState } from "react";
import { Play } from "lucide-react";
import { useSim } from "../lib/simulation/store";
import { setFocus } from "../lib/simulation/stream";
import { useCommands } from "../hooks/useCommands";
import { MapCanvas } from "../components/simulation/MapCanvas";
import { MapControls, ToolHint } from "../components/simulation/MapControls";
import { LayersPanel } from "../components/simulation/LayersPanel";
import { DemoStepper } from "../components/simulation/DemoStepper";
import { KpiStrip } from "../components/simulation/KpiStrip";
import { FleetPanel } from "../components/fleet/FleetPanel";
import { OrdersPanel } from "../components/orders/OrdersPanel";
import { Timeline } from "../components/events/Timeline";
import { InspectorPanel } from "../components/inspector/InspectorPanel";

const SPEEDS = [0.5, 1, 2, 4, 8];

function StartPrompt() {
  const snap = useSim((s) => s.snapshot);
  const status = useSim((s) => s.status);
  const cmd = useCommands();
  if (!snap || !status || status.running || snap.t > 0) return null;
  const demo = status.scenario.demo;
  return (
    <div className="overlay glass start-cta">
      <div className="eyebrow" style={{ marginBottom: 6 }}>{demo ? "Guided demo" : "Scenario ready"}</div>
      <h3>{snap.scenario_name}</h3>
      <p>
        {snap.robots.length} robots · {status.scenario.initial_orders} initial delivery requests, then ≈{status.scenario.order_rate_per_min}/min · seed <span className="mono">{snap.seed}</span>.
        {demo ? " Seven scripted phases: congestion, a hidden road closure, replanning, a battery fault and a CRITICAL order." :
          " " + status.scenario.description}
      </p>
      <button className="btn primary" onClick={() => cmd.start()}><Play />Start simulation</button>
      <div className="hint"><span className="kbd">Space</span> start / pause · <span className="kbd">S</span> step · click a robot to inspect it</div>
    </div>
  );
}

export function OperationsPage() {
  const selection = useSim((s) => s.selection);
  const tool = useSim((s) => s.tool);
  const setTool = useSim((s) => s.setTool);
  const openCount = useSim((s) => s.snapshot?.orders.length ?? 0);
  const robotCount = useSim((s) => s.snapshot?.robots.length ?? 0);
  const [tab, setTab] = useState<"fleet" | "orders">("fleet");
  const cmd = useCommands();

  const onRoadTool = useCallback((roadId: number) => {
    const current = useSim.getState().tool;
    setTool(null);
    if (current === "block") cmd.inject({ type: "ROAD_BLOCKED", road_id: roadId }, `Road E-${roadId} closed by operator`);
    else if (current === "traffic") cmd.inject({ type: "TRAFFIC_INCREASE", road_id: roadId, level: "JAMMED" }, `Congestion added around E-${roadId}`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setTool]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input, select, textarea")) return;
      const s = useSim.getState();
      if (e.code === "Space") { e.preventDefault(); cmd.toggle(); }
      else if (e.key === "s" || e.key === "S") { if (!s.status?.running) cmd.step(4); }
      else if (e.key === "R" && e.shiftKey) cmd.reset();
      else if (e.key === "Escape") { if (s.tool) s.setTool(null); else { s.select(null); setFocus(null); } }
      else if (/^[1-5]$/.test(e.key)) cmd.speed(SPEEDS[Number(e.key) - 1]);
      else if (e.key === "[" || e.key === "]") {
        const robots = s.snapshot?.robots ?? [];
        if (!robots.length) return;
        const cur = s.selection?.type === "robot" ? robots.findIndex((r) => r.id === (s.selection as any).id) : -1;
        const next = robots[(cur + (e.key === "]" ? 1 : -1) + robots.length) % robots.length];
        s.select({ type: "robot", id: next.id });
        setFocus(next.id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="ops">
      <aside className="panel left">
        <div className="tabs" role="tablist">
          <button className={tab === "fleet" ? "on" : ""} onClick={() => setTab("fleet")} role="tab">Fleet <span className="count">{robotCount}</span></button>
          <button className={tab === "orders" ? "on" : ""} onClick={() => setTab("orders")} role="tab">Orders <span className="count">{openCount}</span></button>
        </div>
        {tab === "fleet" ? <FleetPanel /> : <OrdersPanel />}
      </aside>

      <section className="mapwrap">
        <MapCanvas onRoadTool={onRoadTool}>
          <MapControls />
          <LayersPanel />
          <DemoStepper />
          <StartPrompt />
          {tool && <ToolHint />}
        </MapCanvas>
      </section>

      <aside className="panel right">
        {selection ? <InspectorPanel /> : (
          <>
            <div className="panel-head"><h2>Decision timeline</h2><span className="spacer" />
              <span className="muted" style={{ fontSize: 11 }}>why the fleet did what it did</span></div>
            <Timeline />
          </>
        )}
      </aside>

      <KpiStrip />
    </div>
  );
}
