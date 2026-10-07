/**
 * Canvas renderer for the logistics district.
 *
 * World units are metres. The camera maps world → screen with a centre point and a zoom
 * (pixels per metre). Everything is redrawn each animation frame; geometry that never
 * changes (block outlines, road batches) is precomputed once per map.
 */
import type { MapRoad, RoadClass, RobotState, RoadState, Snapshot, StaticMap, Zone, RobotDetail, Priority } from "../../lib/types";
import { PRIORITY_COLOR, STATUS_COLOR, TRAFFIC_COLOR } from "../../lib/theme";
import { position } from "../../lib/simulation/motion";
import type { Layers, Pulse, Selection, Tool } from "../../lib/simulation/store";

export interface Camera { cx: number; cy: number; zoom: number }

export interface Geometry {
  map: StaticMap;
  blocks: Record<Zone, Path2D>;
  blockOutline: Path2D;
  roadIdsByClass: Record<RoadClass, number[]>;
}

export type HoverTarget =
  | { type: "robot"; id: string }
  | { type: "node"; id: number }
  | { type: "road"; id: number };

export interface FrameState {
  snapshot: Snapshot | null;
  roads: Map<number, RoadState>;
  selection: Selection | null;
  hover: HoverTarget | null;
  hoverRobot: string | null;
  layers: Layers;
  pulses: Pulse[];
  replanFlash: Map<string, number>;
  focus: RobotDetail | null;
  tool: Tool;
}

const ROAD_WIDTH_M: Record<RoadClass, number> = { arterial: 15, collector: 10.5, local: 7 };
const ROAD_MIN_PX: Record<RoadClass, number> = { arterial: 2.4, collector: 1.6, local: 1.05 };
const ROAD_COLOR: Record<RoadClass, string> = { arterial: "#3a475a", collector: "#2c3644", local: "#222a35" };
const BLOCK_FILL: Record<Zone, string> = {
  industrial: "#1a1811", commercial: "#111922", residential: "#111a16", energy: "#18141f",
};
const ACCENT = "#4fd6c4";
const CRIT = "#ef5a5a";
const PRIORITY_RANK: Record<Priority, number> = { LOW: 0, NORMAL: 1, HIGH: 2, CRITICAL: 3 };

export function buildGeometry(map: StaticMap): Geometry {
  const blocks = { industrial: new Path2D(), commercial: new Path2D(), residential: new Path2D(), energy: new Path2D() };
  const blockOutline = new Path2D();
  for (const face of map.faces) {
    const pts = face.nodes.map((id) => map.nodes[id]);
    const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
    const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
    const inset = pts.map((p) => {
      const dx = cx - p.x, dy = cy - p.y;
      const d = Math.hypot(dx, dy) || 1;
      const k = Math.min(0.34, 11 / d);
      return [p.x + dx * k, p.y + dy * k];
    });
    for (const path of [blocks[face.zone], blockOutline]) {
      path.moveTo(inset[0][0], inset[0][1]);
      for (let i = 1; i < inset.length; i++) path.lineTo(inset[i][0], inset[i][1]);
      path.closePath();
    }
  }
  const roadIdsByClass: Record<RoadClass, number[]> = { arterial: [], collector: [], local: [] };
  for (const r of map.roads) roadIdsByClass[r.class].push(r.id);
  return { map, blocks, blockOutline, roadIdsByClass };
}

export function fitCamera(map: StaticMap, w: number, h: number, pad = 36): Camera {
  const zoom = Math.min((w - pad * 2) / map.width, (h - pad * 2) / map.height);
  return { cx: map.width / 2, cy: map.height / 2, zoom: Math.max(0.05, zoom) };
}

export function toScreen(cam: Camera, w: number, h: number, x: number, y: number): [number, number] {
  return [(x - cam.cx) * cam.zoom + w / 2, (y - cam.cy) * cam.zoom + h / 2];
}

export function toWorld(cam: Camera, w: number, h: number, sx: number, sy: number): [number, number] {
  return [(sx - w / 2) / cam.zoom + cam.cx, (sy - h / 2) / cam.zoom + cam.cy];
}

function roadPx(cls: RoadClass, zoom: number) {
  return Math.max(ROAD_MIN_PX[cls], ROAD_WIDTH_M[cls] * zoom);
}

function halo(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, fill: string) {
  ctx.lineWidth = 3;
  ctx.strokeStyle = "rgba(7,9,12,0.92)";
  ctx.strokeText(text, x, y);
  ctx.fillStyle = fill;
  ctx.fillText(text, x, y);
}

function strokeRoad(ctx: CanvasRenderingContext2D, map: StaticMap, road: MapRoad) {
  const a = map.nodes[road.a], b = map.nodes[road.b];
  ctx.moveTo(a.x, a.y);
  ctx.lineTo(b.x, b.y);
}

/** Static base: ground, blocks, road network, district labels. Drawn in world space. */
export function drawBase(ctx: CanvasRenderingContext2D, w: number, h: number, cam: Camera, geo: Geometry,
                         opts: { blocks: boolean; labels: boolean; dimRoads?: boolean }) {
  const { map } = geo;
  ctx.fillStyle = "#07090c";
  ctx.fillRect(0, 0, w, h);

  ctx.save();
  ctx.translate(w / 2, h / 2);
  ctx.scale(cam.zoom, cam.zoom);
  ctx.translate(-cam.cx, -cam.cy);

  if (opts.blocks) {
    for (const zone of Object.keys(geo.blocks) as Zone[]) {
      ctx.fillStyle = BLOCK_FILL[zone];
      ctx.fill(geo.blocks[zone]);
    }
    ctx.lineWidth = 1 / cam.zoom;
    ctx.strokeStyle = "rgba(160,175,195,0.06)";
    ctx.stroke(geo.blockOutline);
  }

  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const cls of ["local", "collector", "arterial"] as RoadClass[]) {
    ctx.beginPath();
    for (const id of geo.roadIdsByClass[cls]) strokeRoad(ctx, map, map.roads[id]);
    ctx.strokeStyle = opts.dimRoads ? "#171c24" : ROAD_COLOR[cls];
    ctx.lineWidth = roadPx(cls, cam.zoom) / cam.zoom;
    ctx.stroke();
  }
  if (cam.zoom > 0.5 && !opts.dimRoads) {
    ctx.beginPath();
    for (const id of geo.roadIdsByClass.arterial) strokeRoad(ctx, map, map.roads[id]);
    ctx.setLineDash([6 / cam.zoom, 7 / cam.zoom]);
    ctx.strokeStyle = "rgba(220,230,240,0.07)";
    ctx.lineWidth = 1 / cam.zoom;
    ctx.stroke();
    ctx.setLineDash([]);
  }
  ctx.restore();

  if (opts.labels) {
    ctx.font = "600 10px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    (ctx as any).letterSpacing = "2px";
    for (const d of map.districts) {
      const [x, y] = toScreen(cam, w, h, d.x, d.y);
      ctx.fillStyle = "rgba(200,212,228,0.16)";
      ctx.fillText(d.name.toUpperCase(), x, y);
    }
    (ctx as any).letterSpacing = "0px";
  }
}

function routePath(ctx: CanvasRenderingContext2D, cam: Camera, w: number, h: number, map: StaticMap,
                   start: [number, number] | null, nodes: number[]) {
  ctx.beginPath();
  let first = true;
  if (start) {
    ctx.moveTo(start[0], start[1]);
    first = false;
  }
  for (const id of nodes) {
    const n = map.nodes[id];
    const [x, y] = toScreen(cam, w, h, n.x, n.y);
    if (first) { ctx.moveTo(x, y); first = false; } else ctx.lineTo(x, y);
  }
}

function drawCharger(ctx: CanvasRenderingContext2D, x: number, y: number, s: number, available: boolean) {
  ctx.beginPath();
  ctx.roundRect(x - s, y - s, s * 2, s * 2, 3);
  ctx.fillStyle = "#0e1a14";
  ctx.fill();
  ctx.lineWidth = 1.4;
  ctx.strokeStyle = available ? "#5ec27a" : CRIT;
  ctx.stroke();
  ctx.beginPath();
  const k = s / 7;
  ctx.moveTo(x + 1 * k, y - 4.5 * k);
  ctx.lineTo(x - 2.5 * k, y + 0.8 * k);
  ctx.lineTo(x + 0.2 * k, y + 0.8 * k);
  ctx.lineTo(x - 1 * k, y + 4.5 * k);
  ctx.lineTo(x + 2.6 * k, y - 0.8 * k);
  ctx.lineTo(x - 0.1 * k, y - 0.8 * k);
  ctx.closePath();
  ctx.fillStyle = available ? "#5ec27a" : CRIT;
  ctx.fill();
}

function drawWarehouse(ctx: CanvasRenderingContext2D, x: number, y: number, s: number) {
  ctx.beginPath();
  ctx.rect(x - s, y - s, s * 2, s * 2);
  ctx.fillStyle = "#1a1710";
  ctx.fill();
  ctx.lineWidth = 1.4;
  ctx.strokeStyle = "#d7a23a";
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x - s * 0.55, y - s * 0.2);
  ctx.lineTo(x + s * 0.55, y - s * 0.2);
  ctx.moveTo(x - s * 0.55, y + s * 0.3);
  ctx.lineTo(x + s * 0.55, y + s * 0.3);
  ctx.strokeStyle = "rgba(215,162,58,0.7)";
  ctx.lineWidth = 1.2;
  ctx.stroke();
}

function batteryColor(pct: number) {
  return pct > 50 ? "#5ec27a" : pct > 20 ? "#f2b544" : CRIT;
}

export function render(ctx: CanvasRenderingContext2D, w: number, h: number, cam: Camera, geo: Geometry,
                       st: FrameState, now: number) {
  const { map } = geo;
  const snap = st.snapshot;
  drawBase(ctx, w, h, cam, geo, { blocks: st.layers.blocks, labels: st.layers.labels });
  const selectedRobot = st.selection?.type === "robot" ? st.selection.id : null;

  // ---- road state: traffic & closures
  ctx.save();
  ctx.translate(w / 2, h / 2);
  ctx.scale(cam.zoom, cam.zoom);
  ctx.translate(-cam.cx, -cam.cy);
  ctx.lineCap = "round";
  if (st.layers.traffic) {
    for (const level of ["moderate", "high", "jammed"] as const) {
      ctx.beginPath();
      let any = false;
      for (const rs of st.roads.values()) {
        if (rs.traffic !== level || rs.blocked) continue;
        strokeRoad(ctx, map, map.roads[rs.id]);
        any = true;
      }
      if (!any) continue;
      ctx.strokeStyle = TRAFFIC_COLOR[level];
      ctx.globalAlpha = level === "moderate" ? 0.55 : 0.85;
      ctx.lineWidth = Math.max(1.6, ROAD_WIDTH_M.collector * 0.55 * cam.zoom) / cam.zoom;
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }
  for (const rs of st.roads.values()) {
    if (!rs.blocked) continue;
    const road = map.roads[rs.id];
    ctx.beginPath();
    strokeRoad(ctx, map, road);
    ctx.strokeStyle = rs.known ? CRIT : "rgba(239,90,90,0.5)";
    ctx.lineWidth = (roadPx(road.class, cam.zoom) + 1.5) / cam.zoom;
    ctx.setLineDash(rs.known ? [4 / cam.zoom, 3 / cam.zoom] : [2 / cam.zoom, 4 / cam.zoom]);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  ctx.restore();

  // closure markers (screen space)
  for (const rs of st.roads.values()) {
    if (!rs.blocked) continue;
    const road = map.roads[rs.id];
    const a = map.nodes[road.a], b = map.nodes[road.b];
    const [x, y] = toScreen(cam, w, h, (a.x + b.x) / 2, (a.y + b.y) / 2);
    ctx.beginPath();
    ctx.arc(x, y, 6.5, 0, Math.PI * 2);
    ctx.fillStyle = "#1d0b0d";
    ctx.fill();
    ctx.lineWidth = 1.4;
    ctx.strokeStyle = CRIT;
    if (!rs.known) ctx.setLineDash([2, 2]);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.strokeStyle = CRIT;
    ctx.lineWidth = 1.5;
    if (rs.known) {
      ctx.beginPath();
      ctx.moveTo(x - 2.6, y - 2.6); ctx.lineTo(x + 2.6, y + 2.6);
      ctx.moveTo(x + 2.6, y - 2.6); ctx.lineTo(x - 2.6, y + 2.6);
      ctx.stroke();
    } else {
      ctx.font = "700 8.5px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = CRIT;
      ctx.fillText("?", x, y + 0.5);
    }
  }

  // ---- tool / hover highlight on a road
  if (st.hover?.type === "road" || st.selection?.type === "road") {
    const ids = new Set<number>();
    if (st.hover?.type === "road") ids.add(st.hover.id);
    if (st.selection?.type === "road") ids.add(st.selection.id);
    for (const id of ids) {
      const road = map.roads[id];
      ctx.beginPath();
      const a = toScreen(cam, w, h, map.nodes[road.a].x, map.nodes[road.a].y);
      const b = toScreen(cam, w, h, map.nodes[road.b].x, map.nodes[road.b].y);
      ctx.moveTo(a[0], a[1]);
      ctx.lineTo(b[0], b[1]);
      ctx.lineCap = "round";
      ctx.strokeStyle = st.tool === "block" ? "rgba(239,90,90,0.75)" : st.tool === "traffic" ? "rgba(229,121,59,0.8)" : "rgba(79,214,196,0.65)";
      ctx.lineWidth = roadPx(road.class, cam.zoom) + 5;
      ctx.stroke();
    }
  }

  if (!snap) return;
  const robotPos = new Map<string, { x: number; y: number; heading: number }>();
  for (const r of snap.robots) {
    const p = position(r.id, now);
    const [x, y] = toScreen(cam, w, h, p?.x ?? r.x, p?.y ?? r.y);
    robotPos.set(r.id, { x, y, heading: p?.heading ?? r.heading });
  }

  // ---- routes
  if (st.layers.routes) {
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    for (const r of snap.robots) {
      if (r.id === selectedRobot || !r.route.length) continue;
      const p = robotPos.get(r.id)!;
      routePath(ctx, cam, w, h, map, [p.x, p.y], r.route);
      ctx.strokeStyle = STATUS_COLOR[r.status];
      ctx.globalAlpha = selectedRobot ? 0.1 : r.id === st.hoverRobot ? 0.7 : 0.26;
      ctx.lineWidth = r.id === st.hoverRobot ? 2.2 : 1.5;
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }
  // invalidated routes (fade out over 45 simulated seconds)
  for (const r of snap.robots) {
    if (!r.invalidated_route || r.invalidated_at == null) continue;
    if (selectedRobot && r.id !== selectedRobot) continue;
    const age = snap.t - r.invalidated_at;
    const alpha = 0.85 * Math.max(0, 1 - age / 45);
    if (alpha <= 0.02) continue;
    routePath(ctx, cam, w, h, map, null, r.invalidated_route);
    ctx.setLineDash([5, 4]);
    ctx.strokeStyle = CRIT;
    ctx.globalAlpha = alpha;
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.globalAlpha = 1;
    if (r.id === selectedRobot && r.invalidated_route.length > 1) {
      const mid = map.nodes[r.invalidated_route[Math.min(r.invalidated_route.length - 1, 2)]];
      const [x, y] = toScreen(cam, w, h, mid.x, mid.y);
      ctx.font = "600 9.5px Inter, sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.globalAlpha = Math.min(1, alpha + 0.15);
      halo(ctx, "OLD ROUTE · INVALIDATED", x + 8, y - 8, "#ff9a9a");
      ctx.globalAlpha = 1;
    }
  }
  // selected route
  if (selectedRobot) {
    const r = snap.robots.find((x) => x.id === selectedRobot);
    const p = r && robotPos.get(r.id);
    if (r && p && r.route.length) {
      routePath(ctx, cam, w, h, map, [p.x, p.y], r.route);
      ctx.save();
      ctx.shadowColor = "rgba(79,214,196,0.55)";
      ctx.shadowBlur = 10;
      ctx.strokeStyle = ACCENT;
      ctx.lineWidth = 3;
      ctx.stroke();
      ctx.restore();
      ctx.setLineDash([1.5, 9]);
      ctx.lineDashOffset = -(now / 45);
      ctx.strokeStyle = "rgba(235,255,252,0.75)";
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.lineDashOffset = 0;
      if (r.invalidated_route && r.invalidated_at != null && snap.t - r.invalidated_at < 45) {
        const n = map.nodes[r.route[Math.min(r.route.length - 1, 2)]];
        const [x, y] = toScreen(cam, w, h, n.x, n.y);
        ctx.font = "600 9.5px Inter, sans-serif";
        ctx.textAlign = "left";
        halo(ctx, "NEW ROUTE · ACTIVE", x + 8, y + 10, ACCENT);
      }
    }
    // upcoming stops beyond the current leg
    const stops = st.focus?.id === selectedRobot ? st.focus.stops : [];
    if (stops.length) {
      let prev = r && r.route.length ? map.nodes[r.route[r.route.length - 1]] : null;
      stops.forEach((s, i) => {
        const n = map.nodes[s.node];
        const [x, y] = toScreen(cam, w, h, n.x, n.y);
        if (prev && i > 0) {
          const [px, py] = toScreen(cam, w, h, prev.x, prev.y);
          ctx.beginPath();
          ctx.moveTo(px, py);
          ctx.lineTo(x, y);
          ctx.setLineDash([2, 5]);
          ctx.strokeStyle = "rgba(79,214,196,0.45)";
          ctx.lineWidth = 1.3;
          ctx.stroke();
          ctx.setLineDash([]);
        }
        prev = n;
        ctx.beginPath();
        ctx.arc(x, y, i === 0 ? 11 : 8, 0, Math.PI * 2);
        ctx.strokeStyle = i === 0 ? ACCENT : "rgba(79,214,196,0.5)";
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.font = "600 9.5px Inter, sans-serif";
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        halo(ctx, `${i + 1} · ${s.kind} ${s.name}`, x + 14, y, i === 0 ? ACCENT : "rgba(170,230,222,0.8)");
      });
    }
  }

  // ---- points of interest
  const inbound = new Map<number, Priority>();
  const waiting = new Map<number, number>();
  for (const o of snap.orders) {
    const cur = inbound.get(o.destination);
    if (!cur || PRIORITY_RANK[o.priority] > PRIORITY_RANK[cur]) inbound.set(o.destination, o.priority);
    if (o.status !== "IN_TRANSIT") waiting.set(o.source, (waiting.get(o.source) ?? 0) + 1);
  }
  const chargerState = new Map(snap.chargers.map((c) => [c.node, c]));
  const showIntersections = cam.zoom > 0.95;
  ctx.textBaseline = "middle";
  for (const n of map.nodes) {
    const [x, y] = toScreen(cam, w, h, n.x, n.y);
    if (x < -40 || y < -40 || x > w + 40 || y > h + 40) continue;
    const hovered = st.hover?.type === "node" && st.hover.id === n.id;
    const selected = st.selection?.type === "node" && st.selection.id === n.id;
    if (n.kind === "intersection") {
      if (!showIntersections && !hovered) continue;
      ctx.beginPath();
      ctx.arc(x, y, hovered ? 3 : 1.6, 0, Math.PI * 2);
      ctx.fillStyle = hovered ? ACCENT : "rgba(170,185,205,0.3)";
      ctx.fill();
      continue;
    }
    if (n.kind === "customer") {
      const pr = inbound.get(n.id);
      ctx.beginPath();
      ctx.arc(x, y, 2.8, 0, Math.PI * 2);
      ctx.fillStyle = pr ? "#c9d6e6" : "rgba(150,166,186,0.55)";
      ctx.fill();
      if (pr) {
        ctx.beginPath();
        ctx.arc(x, y, pr === "CRITICAL" ? 7 + Math.sin(now / 180) * 1.2 : 6, 0, Math.PI * 2);
        ctx.strokeStyle = PRIORITY_COLOR[pr];
        ctx.lineWidth = pr === "CRITICAL" ? 1.8 : 1.2;
        ctx.globalAlpha = pr === "LOW" ? 0.5 : 0.9;
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
      if (cam.zoom > 0.75 || hovered || selected) {
        ctx.font = "500 9.5px 'JetBrains Mono', monospace";
        ctx.textAlign = "left";
        halo(ctx, n.name, x + 7, y - 7, "rgba(170,185,205,0.75)");
      }
    } else if (n.kind === "warehouse") {
      drawWarehouse(ctx, x, y, 6.5);
      ctx.font = "600 10px 'JetBrains Mono', monospace";
      ctx.textAlign = "left";
      const count = waiting.get(n.id);
      halo(ctx, count ? `${n.name} · ${count}` : n.name, x + 10, y, "#e3c27c");
    } else if (n.kind === "charger") {
      const cs = chargerState.get(n.id);
      drawCharger(ctx, x, y, 7, cs?.available ?? true);
      if (cs) {
        for (let i = 0; i < cs.slots; i++) {
          const bx = x - (cs.slots * 5 - 1) / 2 + i * 5;
          ctx.fillStyle = i < cs.charging.length ? "#5ec27a" : "rgba(94,194,122,0.22)";
          ctx.fillRect(bx, y + 10, 4, 3);
        }
      }
      ctx.font = "600 10px 'JetBrains Mono', monospace";
      ctx.textAlign = "left";
      const q = cs && cs.queue.length ? ` · queue ${cs.queue.length}` : "";
      halo(ctx, `${n.name}${q}`, x + 11, y, "#9fdcb2");
    }
    if (selected || hovered) {
      ctx.beginPath();
      ctx.arc(x, y, 13, 0, Math.PI * 2);
      ctx.strokeStyle = ACCENT;
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
  }

  // ---- robots
  const radius = Math.min(8.5, Math.max(5, 4 + cam.zoom * 4));
  const order: RobotState[] = [...snap.robots].sort((a, b) =>
    (a.id === selectedRobot ? 1 : 0) - (b.id === selectedRobot ? 1 : 0));
  for (const r of order) {
    const p = robotPos.get(r.id)!;
    const color = STATUS_COLOR[r.status];
    const isSel = r.id === selectedRobot;
    const isHover = r.id === st.hoverRobot || (st.hover?.type === "robot" && st.hover.id === r.id);
    ctx.globalAlpha = selectedRobot && !isSel && !isHover ? 0.5 : 1;

    const flash = st.replanFlash.get(r.id);
    if (flash && now - flash < 2400) {
      const k = (now - flash) / 2400;
      for (const off of [0, 0.35]) {
        const kk = k - off;
        if (kk < 0 || kk > 1) continue;
        ctx.beginPath();
        ctx.arc(p.x, p.y, radius + 4 + kk * 22, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(242,181,68,${0.85 * (1 - kk)})`;
        ctx.lineWidth = 1.6;
        ctx.stroke();
      }
    }
    if (isSel) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, radius + 8, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(79,214,196,0.12)";
      ctx.fill();
      ctx.strokeStyle = ACCENT;
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
    // battery arc
    ctx.beginPath();
    ctx.arc(p.x, p.y, radius + 3, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(148,163,184,0.16)";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(p.x, p.y, radius + 3, -Math.PI / 2, -Math.PI / 2 + (Math.PI * 2 * Math.max(0, r.battery_pct)) / 100);
    ctx.strokeStyle = batteryColor(r.battery_pct);
    ctx.stroke();
    // body + heading notch
    ctx.beginPath();
    ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
    ctx.fillStyle = "#0a0d11";
    ctx.fill();
    ctx.lineWidth = 2.2;
    ctx.strokeStyle = color;
    ctx.stroke();
    if (r.status === "EN_ROUTE") {
      const hx = Math.cos(p.heading), hy = Math.sin(p.heading);
      ctx.beginPath();
      ctx.moveTo(p.x + hx * (radius + 0.5), p.y + hy * (radius + 0.5));
      ctx.lineTo(p.x + hx * (radius - 4.5) - hy * 3, p.y + hy * (radius - 4.5) + hx * 3);
      ctx.lineTo(p.x + hx * (radius - 4.5) + hy * 3, p.y + hy * (radius - 4.5) - hx * 3);
      ctx.closePath();
      ctx.fillStyle = color;
      ctx.fill();
    }
    ctx.beginPath();
    ctx.arc(p.x, p.y, r.carrying.length ? 2.4 : 1.4, 0, Math.PI * 2);
    ctx.fillStyle = r.carrying.length ? "#e6ebf1" : color;
    ctx.fill();

    if (isSel || isHover || (st.layers.labels && cam.zoom > 0.42)) {
      ctx.font = `${isSel ? 600 : 500} 10px 'JetBrains Mono', monospace`;
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      halo(ctx, r.id, p.x + radius + 6, p.y - radius - 1, isSel ? "#e6ebf1" : "rgba(200,212,228,0.8)");
    }
    ctx.globalAlpha = 1;
  }

  // ---- event pulses
  for (const pulse of st.pulses) {
    const k = (now - pulse.t0) / 2400;
    if (k < 0 || k > 1) continue;
    const e = 1 - (1 - k) ** 3;
    const [x, y] = toScreen(cam, w, h, pulse.x, pulse.y);
    if (pulse.roadId != null && k < 0.7) {
      const road = map.roads[pulse.roadId];
      const a = toScreen(cam, w, h, map.nodes[road.a].x, map.nodes[road.a].y);
      const b = toScreen(cam, w, h, map.nodes[road.b].x, map.nodes[road.b].y);
      ctx.beginPath();
      ctx.moveTo(a[0], a[1]);
      ctx.lineTo(b[0], b[1]);
      ctx.strokeStyle = pulse.color;
      ctx.globalAlpha = 0.6 * (1 - k / 0.7);
      ctx.lineWidth = roadPx(road.class, cam.zoom) + 7;
      ctx.stroke();
    }
    ctx.beginPath();
    ctx.arc(x, y, 8 + e * 42, 0, Math.PI * 2);
    ctx.strokeStyle = pulse.color;
    ctx.globalAlpha = 0.85 * (1 - k);
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.globalAlpha = 1;
  }
}

function segDist(px: number, py: number, ax: number, ay: number, bx: number, by: number) {
  const dx = bx - ax, dy = by - ay;
  const len2 = dx * dx + dy * dy || 1;
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

export function hitTest(geo: Geometry, cam: Camera, w: number, h: number, sx: number, sy: number,
                        snapshot: Snapshot | null, roadsOnly: boolean): HoverTarget | null {
  const { map } = geo;
  if (!roadsOnly && snapshot) {
    let best: { id: string; d: number } | null = null;
    for (const r of snapshot.robots) {
      const p = position(r.id) ?? r;
      const [x, y] = toScreen(cam, w, h, p.x, p.y);
      const d = Math.hypot(x - sx, y - sy);
      if (d < 12 && (!best || d < best.d)) best = { id: r.id, d };
    }
    if (best) return { type: "robot", id: best.id };
    let node: { id: number; d: number } | null = null;
    for (const n of map.nodes) {
      if (n.kind === "intersection" && cam.zoom < 0.95) continue;
      const [x, y] = toScreen(cam, w, h, n.x, n.y);
      const d = Math.hypot(x - sx, y - sy);
      const reach = n.kind === "customer" || n.kind === "intersection" ? 7 : 11;
      if (d < reach && (!node || d < node.d)) node = { id: n.id, d };
    }
    if (node) return { type: "node", id: node.id };
  }
  const [wx, wy] = toWorld(cam, w, h, sx, sy);
  let road: { id: number; d: number } | null = null;
  for (const r of map.roads) {
    const a = map.nodes[r.a], b = map.nodes[r.b];
    const d = segDist(wx, wy, a.x, a.y, b.x, b.y) * cam.zoom;
    const reach = Math.max(5, roadPx(r.class, cam.zoom) / 2 + 3);
    if (d < reach && (!road || d < road.d)) road = { id: r.id, d };
  }
  return road ? { type: "road", id: road.id } : null;
}

export function niceScale(zoom: number): { meters: number; px: number } {
  const target = 110 / zoom;
  const steps = [25, 50, 100, 200, 250, 500, 1000, 2000];
  const meters = steps.reduce((best, s) => (Math.abs(s - target) < Math.abs(best - target) ? s : best), steps[0]);
  return { meters, px: meters * zoom };
}
