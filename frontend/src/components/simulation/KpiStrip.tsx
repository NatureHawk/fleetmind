import { useSim } from "../../lib/simulation/store";
import { duration, num, pct } from "../../lib/formatters";

/** Live run KPIs. Every value comes from the backend metrics collector. */
export function KpiStrip() {
  const k = useSim((s) => s.snapshot?.kpis);
  const items: { label: string; value: string; unit?: string; tip: string }[] = k ? [
    { label: "Deliveries", value: `${k.orders_delivered}`, unit: `/ ${k.orders_created}`, tip: "Delivered / created orders" },
    { label: "Completion", value: pct(k.completion_rate), tip: "Delivered ÷ (delivered + failed)" },
    { label: "On time", value: pct(k.on_time_rate), tip: "Share of deliveries before deadline" },
    { label: "Avg delivery", value: duration(k.avg_delivery_time), tip: "Order creation → hand-over" },
    { label: "Energy", value: num(k.total_energy_kwh, 2), unit: "kWh", tip: "Total energy drawn by the fleet" },
    { label: "Replans", value: `${k.replans}`, tip: "Route invalidations + congestion reroutes" },
    { label: "Avg route cost", value: num(k.avg_route_cost, 0), unit: "s", tip: "Mean planned travel time per route" },
    { label: "Nodes explored", value: num(k.nodes_explored), unit: k.avg_nodes_explored ? `· ${num(k.avg_nodes_explored, 0)}/search` : "", tip: "Search expansions across all plans" },
    { label: "Utilisation", value: pct(k.robot_utilization), tip: "Time robots spend on deliveries" },
  ] : [];
  return (
    <div className="kpis" role="region" aria-label="Key metrics">
      {items.map((it) => (
        <div className="kpi" key={it.label} title={it.tip}>
          <div className="k">{it.label}</div>
          <div className="v num">{it.value}{it.unit && <small>{it.unit}</small>}</div>
        </div>
      ))}
    </div>
  );
}
