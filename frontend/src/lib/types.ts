// Types mirroring the FleetMind backend payloads (see backend/app/simulation/snapshot.py).

export type NodeKind = "warehouse" | "customer" | "charger" | "intersection";
export type Zone = "industrial" | "commercial" | "residential" | "energy";
export type RoadClass = "arterial" | "collector" | "local";
export type TrafficLabel = "low" | "moderate" | "high" | "jammed";
export type AlgorithmKey = "bfs" | "dfs" | "greedy" | "dijkstra" | "astar";
export type RobotStatus =
  | "IDLE" | "ASSIGNED" | "PLANNING" | "EN_ROUTE" | "WAITING"
  | "LOADING" | "DELIVERING" | "CHARGING" | "REPLANNING" | "OFFLINE";
export type Priority = "LOW" | "NORMAL" | "HIGH" | "CRITICAL";
export type OrderStatus = "PENDING" | "ASSIGNED" | "IN_TRANSIT" | "DELIVERED" | "FAILED" | "CANCELLED";

export interface MapNode { id: number; x: number; y: number; kind: NodeKind; zone: Zone; name: string; degree: number }
export interface MapRoad { id: number; a: number; b: number; length: number; class: RoadClass; name: string }
export interface MapFace { id: number; nodes: number[]; zone: Zone }
export interface District { name: string; zone: Zone; x: number; y: number }

export interface StaticMap {
  seed: number;
  width: number;
  height: number;
  fingerprint: string;
  nodes: MapNode[];
  roads: MapRoad[];
  faces: MapFace[];
  districts: District[];
  chargers: { node: number; slots: number }[];
}

export interface RobotState {
  id: string;
  model: string;
  status: RobotStatus;
  x: number;
  y: number;
  heading: number;
  battery_pct: number;
  capacity: number;
  orders: string[];
  carrying: string[];
  current_order: string | null;
  target: { node: number; kind: "PICKUP" | "DROPOFF" | "CHARGE"; order_id: string | null } | null;
  route: number[];
  invalidated_route: number[] | null;
  invalidated_at: number | null;
  replans: number;
  orders_completed: number;
  low_battery: boolean;
  algorithm: AlgorithmKey | null;
  route_cost: number | null;
}

export interface OrderState {
  id: string;
  source: number;
  destination: number;
  priority: Priority;
  status: OrderStatus;
  created_at: number;
  deadline: number;
  assigned_robot: string | null;
  picked_up_at: number | null;
  delivered_at: number | null;
  late: boolean;
}

export interface RoadState { id: number; traffic: TrafficLabel; blocked: boolean; known: boolean }

export interface ChargerState {
  node: number;
  name: string;
  slots: number;
  charging: string[];
  queue: string[];
  reserved: string[];
  available: boolean;
  unavailable_until: number | null;
  occupancy: number;
  sessions: number;
  energy_delivered_wh: number;
}

export interface Kpis {
  t: number;
  orders_created: number;
  orders_delivered: number;
  orders_failed: number;
  orders_cancelled: number;
  orders_pending: number;
  orders_assigned: number;
  orders_in_transit: number;
  completion_rate: number | null;
  on_time_rate: number | null;
  avg_delivery_time: number | null;
  p90_delivery_time: number | null;
  avg_assignment_wait: number | null;
  total_distance_km: number;
  total_energy_kwh: number;
  energy_per_delivery_wh: number | null;
  searches: number;
  plan_requests: number;
  cache_hits: number;
  nodes_explored: number;
  avg_nodes_explored: number | null;
  avg_planning_ms: number | null;
  avg_route_cost: number | null;
  plan_success_rate: number | null;
  replans: number;
  replan_triggers: Record<string, number>;
  robot_utilization: number | null;
  robots_total: number;
  robots_busy: number;
  robots_charging: number;
  robots_offline: number;
  battery_depletions: number;
  charge_sessions: number;
  preemptions: number;
  assignments: number;
  fleet_messages: number;
}

export type Category =
  | "environment" | "order" | "allocation" | "planning" | "replanning"
  | "battery" | "coordination" | "agent" | "system" | "demo";
export type Severity = "info" | "notice" | "warning" | "critical";

export interface TimelineEntry {
  seq: number;
  t: number;
  category: Category;
  kind: string;
  severity: Severity;
  message: string;
  robot_id: string | null;
  order_id: string | null;
  road_id: number | null;
  node_id: number | null;
  data: Record<string, any>;
}

export interface DemoPhase {
  key: string;
  title: string;
  description: string;
  status: "done" | "active" | "pending";
  at: number | null;
  started_at: number | null;
  note: string;
}

export interface DemoState {
  index: number;
  phases: DemoPhase[];
  next_at: number | null;
  next_in: number | null;
  complete: boolean;
}

export interface PlanInfo {
  algorithm: AlgorithmKey;
  algorithm_name: string;
  purpose: string;
  trigger: string;
  goal: number;
  goal_name: string;
  cost: number;
  hops: number;
  nodes_explored: number;
  nodes_generated: number;
  elapsed_ms: number;
  energy_wh: number;
  planned_at: number;
  cached: boolean;
}

export interface RobotDetail extends RobotState {
  speed_mps: number;
  speed_factor: number;
  battery_wh: number;
  max_battery_wh: number;
  energy_rate_wh_per_m: number;
  node: number | null;
  status_since: number;
  stops: { kind: string; node: number; name: string; order_id: string | null }[];
  plan: PlanInfo | null;
  route_names: string[];
  remaining_energy_pct: number;
  distance_km: number;
  energy_wh: number;
  energy_pct_used: number;
  energy_charged_wh: number;
  stats: {
    plans: number; replans: number; orders_completed: number; charge_sessions: number; depletions: number;
    idle_time: number; busy_time: number; charging_time: number; offline_time: number; utilization: number;
  };
  loop: { phase: "PERCEIVE" | "DECIDE" | "ACT" | "REPLAN"; perceive: string; decide: string; decide_t: number; act: string };
  decisions: { t: number; phase: string; message: string }[];
  wait_reason: string | null;
  offline_reason: string | null;
}

export interface Snapshot {
  type: "snapshot";
  t: number;
  tick: number;
  running: boolean;
  speed: number;
  scenario: string;
  scenario_name: string;
  seed: number;
  algorithm: AlgorithmKey;
  heuristic: string;
  robots: RobotState[];
  orders: OrderState[];
  recent_orders: OrderState[];
  roads: RoadState[];
  chargers: ChargerState[];
  kpis: Kpis;
  events: TimelineEntry[];
  last_seq: number;
  demo: DemoState | null;
  upcoming_events: number;
  focus?: RobotDetail | null;
}

export interface ScenarioConfig {
  key: string;
  name: string;
  description: string;
  purpose: string;
  seed: number;
  algorithm: AlgorithmKey;
  heuristic: string;
  robots: number;
  initial_orders: number;
  max_orders: number;
  order_rate_per_min: number;
  priority_weights: Record<Priority, number>;
  traffic_intensity: number;
  congestion_events: number;
  closure_events: number;
  road_failure_probability: number;
  robot_failures: number;
  battery_min: number;
  battery_max: number;
  low_battery_robots: number;
  duration_s: number;
  speed: number;
  preemption: boolean;
  demo: boolean;
}

export interface SimulationStatus {
  running: boolean;
  speed: number;
  speeds: number[];
  t: number;
  tick: number;
  tick_seconds: number;
  sim_seconds_per_second_at_1x: number;
  scenario: ScenarioConfig;
  algorithm: AlgorithmKey;
  heuristic: string;
  run_id: string | null;
  version: number;
  fingerprints: Record<string, string>;
  clients: number;
}

export interface OrderDetail extends OrderState {
  source_name: string;
  destination_name: string;
  assigned_at: number | null;
  delivery_time: number | null;
  time_to_deadline: number | null;
  failure_reason: string | null;
  assignment_count: number;
  explanation: AssignmentExplanation | null;
  history: { t: number; message: string }[];
  timeline?: TimelineEntry[];
}

export interface CandidateEval {
  robot_id: string;
  eligible: boolean;
  rejection: string | null;
  score: number | null;
  components: Record<string, number>;
  pickup_eta: number;
  delivery_eta: number;
  lateness: number;
  battery_now_pct: number;
  battery_after_pct: number;
  queued_orders: number;
}

export interface AssignmentExplanation {
  robot_id: string;
  score: number;
  components: Record<string, number>;
  reasons: string[];
  runner_up: CandidateEval | null;
  candidates: CandidateEval[];
  rejected: { reason: string; count: number }[];
  eligible_count: number;
  policy: string;
  preempted_order: string | null;
  t: number;
}

export interface RoadDetail {
  id: number; name: string; source: number; destination: number; source_name: string; destination_name: string;
  distance: number; road_class: RoadClass; speed_factor: number; traffic_level: TrafficLabel;
  known_traffic_level: TrafficLabel; travel_time: number; planner_cost: number; energy_cost: number;
  blocked: boolean; blocked_known_to_fleet: boolean; status: string; robots_routed: string[];
}

export interface NodeDetail {
  id: number; name: string; kind: NodeKind; zone: Zone; x: number; y: number; degree: number;
  roads: { id: number; name: string; to: string }[];
  station?: ChargerState & { available_capacity: number; inbound: string[] };
  orders_waiting?: string[];
  orders_inbound?: string[];
}

export interface AlgorithmStats {
  requests: number; searches: number; cache_hits: number; successes: number; failures: number;
  success_rate: number | null; nodes_explored: number; avg_nodes_explored: number | null;
  max_nodes_explored: number; avg_nodes_generated: number | null; planning_ms_total: number;
  avg_planning_ms: number | null; avg_route_cost: number | null; avg_hops: number | null;
  purposes: Record<string, number>;
}

export interface AlgorithmInfo {
  key: AlgorithmKey; name: string; short: string; family: string; frontier: string; uses_cost: boolean;
  uses_heuristic: boolean; complete: boolean; optimal: string; time_complexity: string;
  space_complexity: string; purpose: string; fleet_behaviour: string; performs_well: string;
  live: AlgorithmStats | null;
}

export interface TraceResult {
  algorithm: AlgorithmKey; name: string; start: number; goal: number; path: number[]; cost: number;
  success: boolean; nodes_explored: number; nodes_generated: number; max_frontier: number; elapsed_ms: number;
  hops: number; trace: [number, number[]][]; final_frontier: number[];
}

export interface TraceResponse {
  start: number; goal: number; start_name: string; goal_name: string; heuristic: string;
  world_version: number; t: number; results: TraceResult[];
}

export interface MetricStat { mean: number | null; std: number | null; min: number | null; max: number | null; n: number }

export interface ExperimentRun {
  algorithm: AlgorithmKey;
  repetition: number;
  seed: number;
  wall_time_s: number;
  metrics: Record<string, number | null>;
  timeseries: { t: number; delivered: number; energy_wh: number; replans: number; open: number; nodes_explored: number }[];
}

export interface Experiment {
  id: string;
  name: string;
  scenario_key: string;
  seed: number;
  algorithms: AlgorithmKey[];
  repetitions: number;
  duration_s: number;
  status: "running" | "completed" | "failed" | "pending";
  progress: number;
  done?: number;
  total?: number;
  aggregates: Record<string, Record<string, MetricStat>> | null;
  fairness: {
    identical_conditions: boolean;
    repetitions: { repetition: number; seed: number; identical: boolean; fingerprints: Record<string, string[]> }[];
  } | null;
  error: string | null;
  config: ScenarioConfig;
  created_at: string | null;
  completed_at: string | null;
  results?: ExperimentRun[];
}

export interface MetricsResponse {
  global: Kpis;
  algorithms: Record<string, AlgorithmStats>;
  robots: {
    id: string; model: string; status: RobotStatus; battery_pct: number; orders_completed: number;
    distance_km: number; energy_wh: number; idle_time: number; busy_time: number; charging_time: number;
    offline_time: number; utilization: number; replans: number; plans: number; charge_sessions: number;
    depletions: number; current_order: string | null;
  }[];
  timeseries: {
    t: number; delivered: number; failed: number; pending: number; open: number; created: number;
    avg_battery_pct: number; energy_wh: number; distance_m: number; replans: number; busy: number;
    charging: number; offline: number; nodes_explored: number;
  }[];
  recent_plans: {
    t: number; robot_id: string | null; purpose: string; algorithm: AlgorithmKey; nodes_explored: number;
    elapsed_ms: number; cost: number | null; hops: number; success: boolean; cached: boolean;
  }[];
  scenario: ScenarioConfig;
}

export interface Health {
  status: string;
  version: string;
  database: { connected: boolean; dialect?: string; fallback?: boolean; url?: string };
}
