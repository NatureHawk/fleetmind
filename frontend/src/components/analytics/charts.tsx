import { useCallback, useRef, useState, type ReactNode } from "react";

/** Width of an element, tracked with a callback ref so it works even if the element mounts late. */
function useWidth<T extends HTMLElement>() {
  const [width, setWidth] = useState(0);
  const observer = useRef<ResizeObserver | null>(null);
  const ref = useCallback((el: T | null) => {
    observer.current?.disconnect();
    observer.current = null;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(el);
    observer.current = ro;
    setWidth(el.getBoundingClientRect().width);
  }, []);
  return [ref, width] as const;
}

export function niceTicks(max: number, count = 4): number[] {
  if (!(max > 0)) return [0, 1];
  const raw = max / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const ticks = [];
  for (let v = 0; v <= max + step * 0.001; v += step) ticks.push(+v.toFixed(10));
  if (ticks[ticks.length - 1] < max) ticks.push(+(ticks[ticks.length - 1] + step).toFixed(10));
  return ticks;
}

/** Rounded-end horizontal bar path: square at the baseline, 4px radius at the data end. */
function hbar(x: number, y: number, w: number, h: number, r = 4) {
  const rr = Math.min(r, w, h / 2);
  if (w <= 0) return "";
  return `M${x},${y} H${x + w - rr} Q${x + w},${y} ${x + w},${y + rr} V${y + h - rr} Q${x + w},${y + h} ${x + w - rr},${y + h} H${x} Z`;
}

/* ------------------------------------------------------------------ bar chart */

export interface BarDatum {
  key: string;
  label: string;
  value: number | null;
  color: string;
  /** Optional spread (e.g. standard deviation) shown as a whisker and in the tooltip. */
  spread?: number | null;
  highlight?: boolean;
}

export function BarChart({ data, format, unit, emptyText = "No data" }: {
  data: BarDatum[]; format: (v: number) => string; unit?: string; emptyText?: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const valid = data.filter((d) => d.value != null);
  const rowH = 30;
  const barH = 14;
  const labelW = 74;
  const valueW = 70;
  const plotW = Math.max(40, width - labelW - valueW);
  const max = Math.max(...valid.map((d) => (d.value ?? 0) + (d.spread ?? 0)), 0);
  const ticks = niceTicks(max, 3);
  const top = ticks[ticks.length - 1] || 1;
  const height = data.length * rowH + 18;
  if (!valid.length) return <div className="empty" style={{ padding: 18 }}>{emptyText}</div>;
  return (
    <div ref={ref} style={{ position: "relative" }}>
      {width > 0 && (
        <svg className="chart" width={width} height={height} role="img"
             aria-label={data.map((d) => `${d.label}: ${d.value == null ? "n/a" : format(d.value)}`).join(", ")}>
          <g className="grid">
            {ticks.map((t) => (
              <g key={t} transform={`translate(${labelW + (t / top) * plotW},0)`}>
                <line y1={0} y2={data.length * rowH} />
                <text y={data.length * rowH + 13} textAnchor="middle">{format(t)}</text>
              </g>
            ))}
          </g>
          {data.map((d, i) => {
            const y = i * rowH + (rowH - barH) / 2;
            const w = d.value == null ? 0 : (d.value / top) * plotW;
            const tip = d.value == null ? w : Math.max(w, ((d.value + (d.spread ?? 0)) / top) * plotW);
            return (
              <g key={d.key} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                <rect x={0} y={i * rowH} width={width} height={rowH} fill={hover === i ? "rgba(148,163,184,0.05)" : "transparent"} />
                <text className="label" x={0} y={i * rowH + rowH / 2 + 4} style={{ fontWeight: d.highlight ? 600 : 400 }}>{d.label}</text>
                <path d={hbar(labelW, y, w, barH)} fill={d.color} opacity={hover == null || hover === i ? 1 : 0.55} />
                {d.spread != null && d.spread > 0 && d.value != null && (
                  <line x1={labelW + ((d.value - d.spread) / top) * plotW} x2={labelW + ((d.value + d.spread) / top) * plotW}
                        y1={y + barH / 2} y2={y + barH / 2} stroke="var(--text-1)" strokeWidth={1} />
                )}
                <text className="value" x={labelW + tip + 8} y={i * rowH + rowH / 2 + 4}>
                  {d.value == null ? "n/a" : format(d.value)}
                </text>
              </g>
            );
          })}
        </svg>
      )}
      {hover != null && data[hover] && (
        <div className="chart-tooltip" style={{ left: Math.min(width - 150, labelW + 20), top: hover * rowH + rowH }}>
          <div className="t">{data[hover].label}</div>
          <div className="r"><i style={{ background: data[hover].color }} />Value<b>{data[hover].value == null ? "n/a" : format(data[hover].value!)}{unit ? ` ${unit}` : ""}</b></div>
          {data[hover].spread != null && <div className="r"><i style={{ background: "transparent" }} />± std<b>{format(data[hover].spread!)}</b></div>}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ line chart */

export interface Series {
  key: string;
  label: string;
  color: string;
  points: { x: number; y: number }[];
}

export function LineChart({ series, height = 200, formatX, formatY, area = false, yLabel }: {
  series: Series[]; height?: number; formatX: (x: number) => string; formatY: (y: number) => string;
  area?: boolean; yLabel?: ReactNode;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hoverX, setHoverX] = useState<number | null>(null);
  const all = series.flatMap((s) => s.points);
  if (all.length < 2) return <div className="empty" style={{ padding: 18 }}>Collecting samples…</div>;
  const padL = 44, padR = 14, padT = 8, padB = 22;
  const xs = all.map((p) => p.x);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const ticks = niceTicks(Math.max(...all.map((p) => p.y)), 4);
  const maxY = ticks[ticks.length - 1] || 1;
  const plotW = Math.max(10, width - padL - padR);
  const plotH = height - padT - padB;
  const sx = (x: number) => padL + ((x - minX) / (maxX - minX || 1)) * plotW;
  const sy = (y: number) => padT + plotH - (y / maxY) * plotH;
  const xTicks = niceTicks(maxX - minX, 5).map((t) => t + minX).filter((t) => t <= maxX);
  const nearest = (s: Series, x: number) => s.points.reduce((b, p) => (Math.abs(p.x - x) < Math.abs(b.x - x) ? p : b), s.points[0]);
  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - r.left;
    if (px < padL || px > padL + plotW) { setHoverX(null); return; }
    setHoverX(minX + ((px - padL) / plotW) * (maxX - minX));
  };
  const hx = hoverX == null ? null : nearest(series.find((s) => s.points.length) ?? series[0], hoverX).x;
  return (
    <div ref={ref} style={{ position: "relative" }}>
      {series.length > 1 && (
        <div className="chart-legend">
          {series.map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.label}</span>)}
          {yLabel && <span className="muted" style={{ marginLeft: "auto" }}>{yLabel}</span>}
        </div>
      )}
      {series.length === 1 && yLabel && <div className="chart-legend"><span className="muted">{yLabel}</span></div>}
      {width > 0 && (
        <svg className="chart" width={width} height={height} onMouseMove={onMove} onMouseLeave={() => setHoverX(null)} role="img"
             aria-label={series.map((s) => `${s.label}: latest ${formatY(s.points[s.points.length - 1]?.y ?? 0)}`).join("; ")}>
          <g className="grid">
            {ticks.map((t) => (
              <g key={t}>
                <line x1={padL} x2={padL + plotW} y1={sy(t)} y2={sy(t)} />
                <text x={padL - 8} y={sy(t) + 3.5} textAnchor="end">{formatY(t)}</text>
              </g>
            ))}
          </g>
          {xTicks.map((t) => <text key={t} x={sx(t)} y={height - 5} textAnchor="middle">{formatX(t)}</text>)}
          {series.map((s) => {
            if (s.points.length < 1) return null;
            const d = s.points.map((p, i) => `${i ? "L" : "M"}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(" ");
            const last = s.points[s.points.length - 1];
            return (
              <g key={s.key}>
                {area && <path d={`${d} L${sx(last.x)},${sy(0)} L${sx(s.points[0].x)},${sy(0)} Z`} fill={s.color} opacity={0.1} />}
                <path d={d} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
                <circle cx={sx(last.x)} cy={sy(last.y)} r={4} fill={s.color} stroke="var(--bg-1)" strokeWidth={2} />
              </g>
            );
          })}
          {hx != null && (
            <g>
              <line x1={sx(hx)} x2={sx(hx)} y1={padT} y2={padT + plotH} stroke="var(--line-3)" />
              {series.map((s) => {
                if (!s.points.length) return null;
                const p = nearest(s, hx);
                return <circle key={s.key} cx={sx(p.x)} cy={sy(p.y)} r={4} fill={s.color} stroke="var(--bg-1)" strokeWidth={2} />;
              })}
            </g>
          )}
        </svg>
      )}
      {hx != null && (
        <div className="chart-tooltip" style={{ left: Math.min(Math.max(sx(hx) + 12, 0), width - 170), top: 28 }}>
          <div className="t mono">{formatX(hx)}</div>
          {series.map((s) => s.points.length > 0 && (
            <div className="r" key={s.key}><i style={{ background: s.color }} />{s.label}<b>{formatY(nearest(s, hx).y)}</b></div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ stat tile */

export function StatTile({ label, value, unit, detail }: { label: string; value: string; unit?: string; detail?: ReactNode }) {
  return (
    <div className="card stat-tile">
      <div className="k">{label}</div>
      <div className="v">{value}{unit && <small>{unit}</small>}</div>
      {detail && <div className="d">{detail}</div>}
    </div>
  );
}
