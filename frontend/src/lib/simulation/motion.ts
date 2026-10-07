/**
 * Smooth robot motion between server snapshots.
 *
 * The server simulates in fixed ticks and streams ~15 snapshots/s; the map renders at the
 * display refresh rate. Each robot glides from where it is drawn now to its latest
 * reported position over one snapshot interval. This is presentation only — the
 * simulation state itself is never interpolated or extrapolated.
 */

interface Track {
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
  heading: number;
  t0: number;
  dur: number;
}

const tracks = new Map<string, Track>();
let lastSnapshotAt = 0;
let interval = 1000 / 15;

export function updateTargets(robots: { id: string; x: number; y: number; heading: number }[], teleport = false) {
  const now = performance.now();
  if (lastSnapshotAt) interval = Math.min(250, Math.max(30, 0.8 * interval + 0.2 * (now - lastSnapshotAt)));
  lastSnapshotAt = now;
  const seen = new Set<string>();
  for (const r of robots) {
    seen.add(r.id);
    const cur = tracks.get(r.id);
    if (!cur || teleport) {
      tracks.set(r.id, { fromX: r.x, fromY: r.y, toX: r.x, toY: r.y, heading: r.heading, t0: now, dur: interval });
      continue;
    }
    const p = position(r.id, now)!;
    const jump = Math.hypot(r.x - p.x, r.y - p.y);
    tracks.set(r.id, {
      fromX: jump > 600 ? r.x : p.x,
      fromY: jump > 600 ? r.y : p.y,
      toX: r.x,
      toY: r.y,
      heading: r.heading,
      t0: now,
      dur: interval,
    });
  }
  for (const id of [...tracks.keys()]) if (!seen.has(id)) tracks.delete(id);
}

export function position(id: string, now = performance.now()): { x: number; y: number; heading: number } | null {
  const t = tracks.get(id);
  if (!t) return null;
  const k = Math.min(1, Math.max(0, (now - t.t0) / t.dur));
  return { x: t.fromX + (t.toX - t.fromX) * k, y: t.fromY + (t.toY - t.fromY) * k, heading: t.heading };
}

export function clearTracks() {
  tracks.clear();
  lastSnapshotAt = 0;
}
