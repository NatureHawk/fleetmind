import { useSim } from "../../lib/simulation/store";
import { RobotInspector, closeSelection } from "./RobotInspector";
import { OrderInspector } from "./OrderInspector";
import { NodeInspector, RoadInspector } from "./PlaceInspectors";

export function InspectorPanel() {
  const sel = useSim((s) => s.selection);
  if (!sel) return null;
  if (sel.type === "robot") return <RobotInspector key={sel.id} id={sel.id} onClose={closeSelection} />;
  if (sel.type === "order") return <OrderInspector key={sel.id} id={sel.id} onClose={closeSelection} />;
  if (sel.type === "road") return <RoadInspector key={sel.id} id={sel.id} onClose={closeSelection} />;
  return <NodeInspector key={sel.id} id={sel.id} onClose={closeSelection} />;
}
