import type { AlgorithmKey, Category, Priority, RobotStatus, TrafficLabel, Zone } from "./types";

/** Robot status colours (status-like states; each is always paired with a text label). */
export const STATUS_COLOR: Record<RobotStatus, string> = {
  IDLE: "#7b8798",
  ASSIGNED: "#8fb8ff",
  PLANNING: "#8fb8ff",
  EN_ROUTE: "#4fd6c4",
  WAITING: "#c3a3f7",
  LOADING: "#a98cf5",
  DELIVERING: "#a98cf5",
  CHARGING: "#5ec27a",
  REPLANNING: "#f2b544",
  OFFLINE: "#ef6a6a",
};

/** Algorithm identity colours — validated categorical order (dark surface, all checks pass). */
export const ALGORITHM_COLOR: Record<AlgorithmKey, string> = {
  bfs: "#3987e5",
  dfs: "#d95926",
  greedy: "#199e70",
  dijkstra: "#c98500",
  astar: "#d55181",
};

export const ALGORITHM_ORDER: AlgorithmKey[] = ["bfs", "dfs", "greedy", "dijkstra", "astar"];
export const ALGORITHM_SHORT: Record<AlgorithmKey, string> = {
  bfs: "BFS", dfs: "DFS", greedy: "Greedy", dijkstra: "Dijkstra", astar: "A*",
};

export const TRAFFIC_COLOR: Record<TrafficLabel, string> = {
  low: "transparent",
  moderate: "#d7a23a",
  high: "#e5793b",
  jammed: "#e2494b",
};

export const PRIORITY_COLOR: Record<Priority, string> = {
  LOW: "#6b7787",
  NORMAL: "#8fb8ff",
  HIGH: "#f2b544",
  CRITICAL: "#ef5a5a",
};

export const ZONE_FILL: Record<Zone, string> = {
  industrial: "#1a1712",
  commercial: "#121821",
  residential: "#121a17",
  energy: "#16131d",
};

export const ZONE_LABEL: Record<Zone, string> = {
  industrial: "Industrial",
  commercial: "Commercial",
  residential: "Residential",
  energy: "Energy",
};

export const CATEGORY_LABEL: Record<Category, string> = {
  environment: "Environment",
  order: "Orders",
  allocation: "Allocation",
  planning: "Planning",
  replanning: "Replanning",
  battery: "Battery",
  coordination: "Coordination",
  agent: "Agents",
  system: "System",
  demo: "Demo",
};

export const CATEGORY_COLOR: Record<Category, string> = {
  environment: "#e5793b",
  order: "#8fb8ff",
  allocation: "#4fd6c4",
  planning: "#7b8798",
  replanning: "#f2b544",
  battery: "#5ec27a",
  coordination: "#c3a3f7",
  agent: "#ef6a6a",
  system: "#7b8798",
  demo: "#e6edf3",
};

export const ACCENT = "#4fd6c4";
