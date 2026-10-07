import { STATUS_COLOR, PRIORITY_COLOR } from "../../lib/theme";
import type { Priority, RobotStatus } from "../../lib/types";
import { statusLabel } from "../../lib/formatters";

export function StatusBadge({ status }: { status: RobotStatus }) {
  return (
    <span className="badge soft" style={{ color: STATUS_COLOR[status] }}>
      <i />
      {statusLabel(status)}
    </span>
  );
}

export function PriorityTag({ priority }: { priority: Priority }) {
  return (
    <span className="badge soft" style={{ color: PRIORITY_COLOR[priority] }}>
      {priority}
    </span>
  );
}

export function batteryColor(pct: number) {
  return pct > 50 ? "var(--ok)" : pct > 20 ? "var(--warn)" : "var(--crit)";
}

export function BatteryBar({ pct, width }: { pct: number; width?: number }) {
  return (
    <div className="bar" style={{ width }} role="meter" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}
         aria-label="Battery">
      <span style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: batteryColor(pct) }} />
    </div>
  );
}
