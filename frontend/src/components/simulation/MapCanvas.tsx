import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Crosshair, Minus, Plus, Maximize2 } from "lucide-react";
import { useSim } from "../../lib/simulation/store";
import { setFocus } from "../../lib/simulation/stream";
import { position } from "../../lib/simulation/motion";
import { buildGeometry, fitCamera, hitTest, niceScale, render, type Camera, type HoverTarget } from "./renderer";
import { HoverCard } from "./HoverCard";

interface Props {
  onRoadTool: (roadId: number) => void;
  children?: ReactNode;
}

/** The live map: pan (drag), zoom (wheel), select (click), hover cards and road tools. */
export function MapCanvas({ onRoadTool, children }: Props) {
  const map = useSim((s) => s.map);
  const tool = useSim((s) => s.tool);
  const selection = useSim((s) => s.selection);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const camRef = useRef<Camera | null>(null);
  const sizeRef = useRef({ w: 0, h: 0 });
  const hoverRef = useRef<HoverTarget | null>(null);
  const followRef = useRef(false);
  const [hover, setHover] = useState<{ target: HoverTarget; x: number; y: number } | null>(null);
  const [zoom, setZoom] = useState(0.3);
  const [dragging, setDragging] = useState(false);
  const [follow, setFollow] = useState(false);
  const geo = useMemo(() => (map ? buildGeometry(map) : null), [map]);

  useEffect(() => { followRef.current = follow; }, [follow]);
  useEffect(() => { if (selection?.type !== "robot") setFollow(false); }, [selection]);

  // Fit the camera whenever a new map arrives.
  useEffect(() => {
    if (!map) return;
    const { w, h } = sizeRef.current;
    if (w && h) {
      camRef.current = fitCamera(map, w, h);
      setZoom(camRef.current.zoom);
    } else camRef.current = null;
  }, [map]);

  // Resize + render loop.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !geo) return;
    const ctx = canvas.getContext("2d")!;
    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(rect.width * dpr);
      canvas.height = Math.round(rect.height * dpr);
      sizeRef.current = { w: rect.width, h: rect.height };
      if (!camRef.current) {
        camRef.current = fitCamera(geo.map, rect.width, rect.height);
        setZoom(camRef.current.zoom);
      }
    };
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    resize();
    let raf = 0;
    const frame = () => {
      raf = requestAnimationFrame(frame);
      const cam = camRef.current;
      if (!cam) return;
      const s = useSim.getState();
      const { w, h } = sizeRef.current;
      if (followRef.current && s.selection?.type === "robot") {
        const p = position(s.selection.id);
        if (p) { cam.cx += (p.x - cam.cx) * 0.12; cam.cy += (p.y - cam.cy) * 0.12; }
      }
      const dpr = window.devicePixelRatio || 1;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      render(ctx, w, h, cam, geo, {
        snapshot: s.snapshot, roads: s.roads, selection: s.selection, hover: hoverRef.current,
        hoverRobot: s.hoverRobot, layers: s.layers, pulses: s.pulses, replanFlash: s.replanFlash, focus: s.focus,
        tool: s.tool,
      }, performance.now());
    };
    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  }, [geo]);

  // Pointer interaction.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !geo) return;
    let down: { x: number; y: number; cx: number; cy: number; moved: boolean } | null = null;
    const local = (e: PointerEvent | WheelEvent) => {
      const r = canvas.getBoundingClientRect();
      return [e.clientX - r.left, e.clientY - r.top] as const;
    };
    const onDown = (e: PointerEvent) => {
      const cam = camRef.current;
      if (!cam || e.button !== 0) return;
      const [x, y] = local(e);
      down = { x, y, cx: cam.cx, cy: cam.cy, moved: false };
      canvas.setPointerCapture(e.pointerId);
    };
    const onMove = (e: PointerEvent) => {
      const cam = camRef.current;
      if (!cam) return;
      const [x, y] = local(e);
      if (down) {
        const dx = x - down.x, dy = y - down.y;
        if (!down.moved && Math.hypot(dx, dy) > 4) { down.moved = true; setDragging(true); setFollow(false); }
        if (down.moved) {
          cam.cx = down.cx - dx / cam.zoom;
          cam.cy = down.cy - dy / cam.zoom;
          return;
        }
      }
      const { w, h } = sizeRef.current;
      const t = hitTest(geo, cam, w, h, x, y, useSim.getState().snapshot, useSim.getState().tool !== null);
      hoverRef.current = t;
      setHover(t ? { target: t, x, y } : null);
      useSim.getState().setHoverRobot(t?.type === "robot" ? t.id : null);
    };
    const onUp = (e: PointerEvent) => {
      const cam = camRef.current;
      if (!cam || !down) return;
      const wasDrag = down.moved;
      down = null;
      setDragging(false);
      if (wasDrag) return;
      const [x, y] = local(e);
      const { w, h } = sizeRef.current;
      const s = useSim.getState();
      const t = hitTest(geo, cam, w, h, x, y, s.snapshot, s.tool !== null);
      if (s.tool && t?.type === "road") {
        onRoadTool(t.id);
        return;
      }
      if (!t) { s.select(null); setFocus(null); return; }
      s.select(t);
      setFocus(t.type === "robot" ? t.id : null);
    };
    const onLeave = () => {
      hoverRef.current = null;
      setHover(null);
      useSim.getState().setHoverRobot(null);
    };
    const onWheel = (e: WheelEvent) => {
      const cam = camRef.current;
      if (!cam) return;
      e.preventDefault();
      const [x, y] = local(e);
      const { w, h } = sizeRef.current;
      const before = [(x - w / 2) / cam.zoom + cam.cx, (y - h / 2) / cam.zoom + cam.cy];
      const fit = fitCamera(geo.map, w, h).zoom;
      cam.zoom = Math.min(4, Math.max(fit * 0.6, cam.zoom * Math.exp(-e.deltaY * 0.0014)));
      cam.cx = before[0] - (x - w / 2) / cam.zoom;
      cam.cy = before[1] - (y - h / 2) / cam.zoom;
      setZoom(cam.zoom);
    };
    canvas.addEventListener("pointerdown", onDown);
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerup", onUp);
    canvas.addEventListener("pointerleave", onLeave);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerup", onUp);
      canvas.removeEventListener("pointerleave", onLeave);
      canvas.removeEventListener("wheel", onWheel);
    };
  }, [geo, onRoadTool]);

  // Keyboard: F fit, C centre/follow selection.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input, select, textarea")) return;
      if (e.key === "f" || e.key === "F") fit();
      if (e.key === "c" || e.key === "C") centerOnSelection();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const zoomBy = (k: number) => {
    const cam = camRef.current;
    if (!cam || !geo) return;
    const { w, h } = sizeRef.current;
    const fitZ = fitCamera(geo.map, w, h).zoom;
    cam.zoom = Math.min(4, Math.max(fitZ * 0.6, cam.zoom * k));
    setZoom(cam.zoom);
  };
  const fit = () => {
    if (!geo) return;
    const { w, h } = sizeRef.current;
    camRef.current = fitCamera(geo.map, w, h);
    setZoom(camRef.current.zoom);
    setFollow(false);
  };
  const centerOnSelection = () => {
    const s = useSim.getState();
    const cam = camRef.current;
    if (!cam || !s.selection || !geo) return;
    if (s.selection.type === "robot") { setFollow((f) => !f); if (cam.zoom < 0.6) { cam.zoom = 0.75; setZoom(0.75); } return; }
    let pt: { x: number; y: number } | null = null;
    if (s.selection.type === "node") pt = geo.map.nodes[s.selection.id];
    if (s.selection.type === "road") {
      const r = geo.map.roads[s.selection.id];
      pt = { x: (geo.map.nodes[r.a].x + geo.map.nodes[r.b].x) / 2, y: (geo.map.nodes[r.a].y + geo.map.nodes[r.b].y) / 2 };
    }
    if (pt) { cam.cx = pt.x; cam.cy = pt.y; }
  };

  const scale = niceScale(zoom);
  const cls = ["map-canvas", dragging && "dragging", tool && "tool", !tool && hover && "hovering"].filter(Boolean).join(" ");
  return (
    <>
      <canvas ref={canvasRef} className={cls} aria-label="Simulation map" role="img" />
      {hover && !dragging && (
        <HoverCard target={hover.target} x={hover.x} y={hover.y} />
      )}
      <div className="overlay glass scale" aria-hidden>
        <div className="scale-bar" style={{ width: scale.px }} />
        <span>{scale.meters >= 1000 ? `${scale.meters / 1000} km` : `${scale.meters} m`}</span>
      </div>
      <div className="overlay glass zoom">
        <button className="btn ghost sm icon" onClick={() => zoomBy(1.3)} data-tip="Zoom in" data-tip-pos="left"><Plus /></button>
        <button className="btn ghost sm icon" onClick={() => zoomBy(1 / 1.3)} data-tip="Zoom out" data-tip-pos="left"><Minus /></button>
        <button className="btn ghost sm icon" onClick={fit} data-tip="Fit city (F)" data-tip-pos="left"><Maximize2 /></button>
        <button className={`btn ghost sm icon ${follow ? "active" : ""}`} onClick={centerOnSelection}
                disabled={!selection} data-tip={selection?.type === "robot" ? "Follow robot (C)" : "Centre selection (C)"} data-tip-pos="left">
          <Crosshair />
        </button>
      </div>
      {children}
    </>
  );
}
