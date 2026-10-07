import { create } from "zustand";
import type {
  RobotDetail, RoadState, Snapshot, StaticMap, TimelineEntry, SimulationStatus,
} from "../types";
import { updateTargets, clearTracks } from "./motion";

export type Selection =
  | { type: "robot"; id: string }
  | { type: "road"; id: number }
  | { type: "node"; id: number }
  | { type: "order"; id: string };

export type Tool = "block" | "traffic" | null;

export interface Pulse {
  id: number;
  x: number;
  y: number;
  color: string;
  t0: number;
  /** Optional road to flash (drawn along its geometry). */
  roadId?: number;
}

export interface Layers {
  routes: boolean;
  traffic: boolean;
  labels: boolean;
  blocks: boolean;
}

export interface Toast {
  id: number;
  tone: "info" | "error" | "success";
  message: string;
}

interface SimState {
  connection: "connecting" | "open" | "closed";
  map: StaticMap | null;
  mapVersion: number;
  status: SimulationStatus | null;
  snapshot: Snapshot | null;
  events: TimelineEntry[];
  roads: Map<number, RoadState>;
  focus: RobotDetail | null;
  selection: Selection | null;
  hoverRobot: string | null;
  tool: Tool;
  layers: Layers;
  pulses: Pulse[];
  replanFlash: Map<string, number>;
  toasts: Toast[];

  setConnection: (c: SimState["connection"]) => void;
  setStatic: (map: StaticMap, status: SimulationStatus, version: number) => void;
  applySnapshot: (snap: Snapshot) => void;
  setStatus: (status: SimulationStatus) => void;
  select: (s: Selection | null) => void;
  setHoverRobot: (id: string | null) => void;
  setTool: (t: Tool) => void;
  toggleLayer: (k: keyof Layers) => void;
  toast: (message: string, tone?: Toast["tone"]) => void;
  dismissToast: (id: number) => void;
}

const MAX_EVENTS = 900;
let pulseSeq = 0;
let toastSeq = 0;

const PULSE_KINDS: Record<string, string> = {
  ROAD_BLOCKED: "#ef5a5a",
  CLOSURE_DETECTED: "#ef5a5a",
  TRAFFIC_INCREASE: "#e5793b",
  NEW_ORDER: "#8fb8ff",
  ORDER_DELIVERED: "#5ec27a",
  CHARGE_DIVERSION: "#5ec27a",
  REPLAN_TRIGGERED: "#f2b544",
  PREEMPTION: "#f2b544",
  ROBOT_OFFLINE: "#ef5a5a",
};

function pulsesFor(entries: TimelineEntry[], map: StaticMap, snap: Snapshot): Pulse[] {
  const now = performance.now();
  const out: Pulse[] = [];
  for (const e of entries) {
    const color = PULSE_KINDS[e.kind];
    if (!color) continue;
    if (e.kind === "NEW_ORDER" && e.data?.priority !== "CRITICAL" && e.data?.priority !== "HIGH") continue;
    if (e.road_id != null && (e.kind === "ROAD_BLOCKED" || e.kind === "CLOSURE_DETECTED" || e.kind === "TRAFFIC_INCREASE")) {
      const r = map.roads[e.road_id];
      const a = map.nodes[r.a], b = map.nodes[r.b];
      out.push({ id: ++pulseSeq, x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, color, t0: now, roadId: r.id });
    } else if (e.robot_id && (e.kind === "REPLAN_TRIGGERED" || e.kind === "CHARGE_DIVERSION" || e.kind === "ROBOT_OFFLINE" || e.kind === "PREEMPTION")) {
      const robot = snap.robots.find((r) => r.id === e.robot_id);
      if (robot) out.push({ id: ++pulseSeq, x: robot.x, y: robot.y, color, t0: now });
    } else if (e.node_id != null) {
      const n = map.nodes[e.node_id];
      out.push({ id: ++pulseSeq, x: n.x, y: n.y, color, t0: now });
    }
  }
  return out;
}

export const useSim = create<SimState>((set, get) => ({
  connection: "connecting",
  map: null,
  mapVersion: -1,
  status: null,
  snapshot: null,
  events: [],
  roads: new Map(),
  focus: null,
  selection: null,
  hoverRobot: null,
  tool: null,
  layers: { routes: true, traffic: true, labels: true, blocks: true },
  pulses: [],
  replanFlash: new Map(),
  toasts: [],

  setConnection: (connection) => set({ connection }),

  setStatic: (map, status, version) => {
    clearTracks();
    set({ map, status, mapVersion: version, events: [], snapshot: null, roads: new Map(), focus: null,
          selection: null, pulses: [], replanFlash: new Map() });
  },

  applySnapshot: (snap) => {
    const { map, events, snapshot: prev } = get();
    const fresh = snap.events;
    const merged = fresh.length ? [...events, ...fresh].slice(-MAX_EVENTS) : events;
    updateTargets(snap.robots, !prev);
    const roads = new Map<number, RoadState>();
    for (const r of snap.roads) roads.set(r.id, r);
    let pulses = get().pulses;
    let replanFlash = get().replanFlash;
    if (fresh.length && map && prev) {
      const now = performance.now();
      pulses = [...pulses.filter((p) => now - p.t0 < 2600), ...pulsesFor(fresh, map, snap)];
      const flashes = fresh.filter((e) => e.robot_id && (e.kind === "REPLAN_TRIGGERED" || e.kind === "ROUTE_SWITCHED"));
      if (flashes.length) {
        replanFlash = new Map(replanFlash);
        for (const e of flashes) replanFlash.set(e.robot_id!, now);
      }
    }
    const status = get().status;
    set({
      snapshot: snap,
      events: merged,
      roads,
      focus: snap.focus ?? (get().selection?.type === "robot" ? get().focus : null),
      pulses,
      replanFlash,
      status: status ? { ...status, running: snap.running, speed: snap.speed, t: snap.t, algorithm: snap.algorithm,
                         heuristic: snap.heuristic } : status,
    });
  },

  setStatus: (status) => set({ status }),

  select: (selection) => set({ selection, focus: selection?.type === "robot" ? get().focus : null }),
  setHoverRobot: (hoverRobot) => set({ hoverRobot }),
  setTool: (tool) => set({ tool }),
  toggleLayer: (k) => set({ layers: { ...get().layers, [k]: !get().layers[k] } }),

  toast: (message, tone = "info") => {
    const id = ++toastSeq;
    set({ toasts: [...get().toasts, { id, tone, message }].slice(-4) });
    window.setTimeout(() => get().dismissToast(id), tone === "error" ? 6000 : 3500);
  },
  dismissToast: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
}));
