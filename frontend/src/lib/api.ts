import type {
  AlgorithmInfo, Experiment, Health, MetricsResponse, NodeDetail, OrderDetail, RoadDetail, RobotDetail,
  ScenarioConfig, SimulationStatus, TimelineEntry, TraceResponse,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init ?? {};
  const res = await fetch(`/api${path}`, {
    ...rest,
    headers: json !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = typeof body.detail === "string" ? body.detail
        : Array.isArray(body.detail) ? body.detail.map((d: any) => d.msg).join("; ") : message;
    } catch { /* non-JSON error */ }
    throw new ApiError(res.status, message);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

const post = <T>(path: string, json: unknown = {}) => request<T>(path, { method: "POST", json });

export interface EventPayload {
  type: string;
  road_id?: number;
  road_ids?: number[];
  robot_id?: string;
  order_id?: string;
  node_id?: number;
  level?: string | number;
  priority?: string;
  source?: number;
  destination?: number;
  duration_s?: number;
}

export const api = {
  health: () => request<Health>("/health"),
  status: () => request<SimulationStatus>("/simulation/status"),
  start: () => post<SimulationStatus>("/simulation/start"),
  pause: () => post<SimulationStatus>("/simulation/pause"),
  step: (ticks = 1) => post<SimulationStatus>("/simulation/step", { ticks }),
  reset: (body: { scenario?: string; seed?: number; algorithm?: string; heuristic?: string; config?: ScenarioConfig }) =>
    post<SimulationStatus>("/simulation/reset", body),
  setSpeed: (speed: number) => post<SimulationStatus>("/simulation/speed", { speed }),
  setAlgorithm: (algorithm: string, heuristic?: string) =>
    post<SimulationStatus>("/simulation/algorithm", { algorithm, heuristic }),
  robot: (id: string) => request<RobotDetail & { timeline: TimelineEntry[] }>(`/robots/${id}`),
  order: (id: string) => request<OrderDetail>(`/orders/${id}`),
  road: (id: number) => request<RoadDetail>(`/environment/roads/${id}`),
  node: (id: number) => request<NodeDetail>(`/environment/nodes/${id}`),
  inject: (payload: EventPayload) => post<{ event: unknown; timeline: TimelineEntry[] }>("/events", payload),
  scenarios: () => request<ScenarioConfig[]>("/scenarios"),
  algorithms: () => request<{ active: string; heuristic: string; heuristics: { key: string; description: string }[];
    algorithms: AlgorithmInfo[] }>("/algorithms"),
  trace: (body: { algorithm?: string; start?: number; goal?: number; heuristic?: string }) =>
    post<TraceResponse>("/algorithms/trace", body),
  metrics: () => request<MetricsResponse>("/metrics"),
  experiments: () => request<Experiment[]>("/experiments"),
  experiment: (id: string) => request<Experiment>(`/experiments/${id}`),
  runExperiment: (body: { scenario?: string; config?: ScenarioConfig; seed?: number; algorithms: string[];
    repetitions: number; duration_s: number; name?: string }) => post<Experiment>("/experiments/run", body),
  deleteExperiment: (id: string) => request<void>(`/experiments/${id}`, { method: "DELETE" }),
};
