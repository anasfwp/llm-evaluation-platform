import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent, RefObject } from "react";
import { niceTicks } from "../format";

export interface Series {
  name: string;
  color: string;
}

interface TooltipState {
  x: number;
  y: number;
  title: string;
  rows: { name: string; color: string; value: string }[];
}

function Tooltip({ state }: { state: TooltipState | null }) {
  if (!state) return null;
  return (
    <div className="tooltip" style={{ left: state.x, top: state.y }} role="presentation">
      <div className="title">{state.title}</div>
      {state.rows.map((row) => (
        <div className="row" key={row.name}>
          <span className="key" style={{ background: row.color }} />
          <strong>{row.value}</strong>
          <span className="muted">{row.name}</span>
        </div>
      ))}
    </div>
  );
}

export function Legend({ series, line = false }: { series: Series[]; line?: boolean }) {
  if (series.length < 2) return null;
  return (
    <ul className="legend" aria-label="Legend">
      {series.map((s) => (
        <li key={s.name}>
          <span className={`swatch${line ? " line" : ""}`} style={{ background: s.color }} />
          {s.name}
        </li>
      ))}
    </ul>
  );
}

/**
 * The rendered width of `ref`, tracked with a ResizeObserver. Charts draw at their
 * real pixel size so text stays legible instead of scaling with a fixed viewBox.
 */
function useWidth(ref: RefObject<HTMLElement>, fallback: number): number {
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(([entry]) => {
      const next = Math.floor(entry?.contentRect.width ?? 0);
      if (next > 0) setWidth(next);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}

/** Place a tooltip near (x, y) inside the chart box without spilling off its right edge. */
function placeTooltip(box: HTMLDivElement | null, x: number, y: number): { x: number; y: number } {
  const width = box?.clientWidth ?? 400;
  return { x: Math.min(Math.max(0, x + 12), Math.max(0, width - 180)), y: Math.max(0, y - 12) };
}

export interface BarRow {
  label: string;
  values: (number | null)[]; // one per series
}

/**
 * Horizontal bars: one row per label, one bar per series. A single scale from
 * zero; values are labelled at the bar end, and every bar has a hover/focus tooltip.
 */
export function BarChart({
  title,
  rows,
  series,
  format,
  maxValue,
}: {
  title: string;
  rows: BarRow[];
  series: Series[];
  format: (value: number | null) => string;
  maxValue?: number;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<TooltipState | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const width = useWidth(box, 360);
  const labelWidth = Math.min(120, Math.round(width * 0.28));
  const valueWidth = 72;
  const barHeight = 14;
  const gap = 2;
  const groupGap = 12;
  const groupHeight = series.length * barHeight + (series.length - 1) * gap;
  const top = 4;
  const height = top + rows.length * (groupHeight + groupGap) + 20;
  const finite = rows.flatMap((r) => r.values).filter((v): v is number => v !== null);
  const domainMax = Math.max(maxValue ?? 0, ...finite, 0);
  const plotWidth = width - labelWidth - valueWidth;
  // Roughly one tick per 80px, so tick labels never run into each other.
  const ticks = niceTicks(domainMax || 1, Math.max(2, Math.min(4, Math.floor(plotWidth / 80))));
  const scaleMax = ticks[ticks.length - 1]!;
  const x = (v: number) => labelWidth + (Math.max(0, v) / scaleMax) * plotWidth;

  const show = (row: BarRow, si: number, cx: number, cy: number) => {
    const s = series[si]!;
    setActive(`${row.label}:${si}`);
    setTip({
      ...placeTooltip(box.current, cx, cy),
      title: row.label,
      rows: [{ name: s.name, color: s.color, value: format(row.values[si] ?? null) }],
    });
  };
  const hide = () => {
    setTip(null);
    setActive(null);
  };

  return (
    <figure className="chart" ref={box} style={{ margin: 0 }}>
      <figcaption>
        <h3>{title}</h3>
      </figcaption>
      <Legend series={series} />
      <svg width={width} height={height} role="img" aria-label={`${title} bar chart`}>
        {ticks.map((t) => (
          <g key={t}>
            <line className="gridline" x1={x(t)} x2={x(t)} y1={top} y2={height - 20} />
            <text className="tick" x={x(t)} y={height - 6} textAnchor="middle">
              {format(t)}
            </text>
          </g>
        ))}
        <line className="baseline" x1={x(0)} x2={x(0)} y1={top} y2={height - 20} />
        {rows.map((row, ri) => {
          const y0 = top + ri * (groupHeight + groupGap);
          return (
            <g key={row.label}>
              <text className="label" x={labelWidth - 8} y={y0 + groupHeight / 2 + 4} textAnchor="end">
                {truncate(row.label, Math.floor((labelWidth - 8) / 7))}
              </text>
              {row.values.map((value, si) => {
                const y = y0 + si * (barHeight + gap);
                const s = series[si]!;
                const end = value === null ? x(0) : x(value);
                const w = Math.max(0, end - x(0));
                const key = `${row.label}:${si}`;
                return (
                  <g key={si}>
                    {value !== null && w > 0 && (
                      <path
                        className={`mark${active === key ? " active" : ""}`}
                        fill={s.color}
                        d={roundedRight(x(0), y, w, barHeight, Math.min(4, w))}
                      />
                    )}
                    <text className="value-label" x={end + 6} y={y + barHeight - 3}>
                      {format(value)}
                    </text>
                    <rect
                      className="hit"
                      x={labelWidth}
                      y={y - gap}
                      width={plotWidth + valueWidth}
                      height={barHeight + gap * 2}
                      tabIndex={0}
                      aria-label={`${row.label}, ${s.name}: ${format(value)}`}
                      onPointerMove={(e: PointerEvent<SVGRectElement>) => {
                        const r = box.current?.getBoundingClientRect();
                        show(row, si, e.clientX - (r?.left ?? 0), e.clientY - (r?.top ?? 0));
                      }}
                      onPointerLeave={hide}
                      onFocus={() => show(row, si, end, y + 40)}
                      onBlur={hide}
                    />
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
      <Tooltip state={tip} />
    </figure>
  );
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, Math.max(1, max - 1))}…` : text;
}

/** A bar path anchored flat at the baseline with a rounded data end. */
function roundedRight(x: number, y: number, w: number, h: number, r: number): string {
  return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x}Z`;
}

export interface LinePoint {
  label: string; // x-axis label, e.g. a run date
  values: (number | null)[]; // one per series
}

/**
 * A line per series over ordered points (e.g. runs over time). The crosshair snaps
 * to the nearest point and the tooltip lists every series there.
 */
export function LineChart({
  title,
  points,
  series,
  format,
  onSelect,
}: {
  title: string;
  points: LinePoint[];
  series: Series[];
  format: (value: number | null) => string;
  onSelect?: (index: number) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const id = useId();
  const [hover, setHover] = useState<number | null>(null);
  const width = useWidth(box, 640);
  const height = 240;
  const pad = { left: 48, right: 16, top: 12, bottom: 28 };
  const finite = points.flatMap((p) => p.values).filter((v): v is number => v !== null);
  const ticks = niceTicks(Math.max(...finite, 0) || 1);
  const yMax = ticks[ticks.length - 1]!;
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const x = (i: number) => pad.left + (points.length <= 1 ? plotW / 2 : (i / (points.length - 1)) * plotW);
  const y = (v: number) => pad.top + plotH - (v / yMax) * plotH;

  const paths = useMemo(
    () =>
      series.map((_, si) => {
        let d = "";
        let pen = false;
        points.forEach((p, i) => {
          const v = p.values[si];
          if (v === null || v === undefined) {
            pen = false;
            return;
          }
          d += `${pen ? "L" : "M"}${x(i)},${y(v)}`;
          pen = true;
        });
        return d;
      }),
    [points, series, yMax, width],
  );

  const nearest = (clientX: number): number => {
    const rect = box.current?.querySelector("svg")?.getBoundingClientRect();
    if (!rect || points.length === 0) return 0;
    const vx = clientX - rect.left;
    let best = 0;
    points.forEach((_, i) => {
      if (Math.abs(x(i) - vx) < Math.abs(x(best) - vx)) best = i;
    });
    return best;
  };

  const onKey = (event: KeyboardEvent<SVGSVGElement>) => {
    const current = hover ?? -1;
    if (event.key === "ArrowRight") setHover(Math.min(points.length - 1, current + 1));
    else if (event.key === "ArrowLeft") setHover(Math.max(0, current - 1));
    else if (event.key === "Enter" && hover !== null) onSelect?.(hover);
    else return;
    event.preventDefault();
  };

  const tip: TooltipState | null =
    hover === null || !points[hover]
      ? null
      : {
          ...placeTooltip(box.current, x(hover), pad.top + 30),
          title: points[hover]!.label,
          rows: series.map((s, si) => ({
            name: s.name,
            color: s.color,
            value: format(points[hover]!.values[si] ?? null),
          })),
        };
  const last = points.length - 1;

  return (
    <figure className="chart" ref={box} style={{ margin: 0 }}>
      <figcaption>
        <h3 id={`${id}-title`}>{title}</h3>
      </figcaption>
      <Legend series={series} line />
      <svg
        width={width}
        height={height}
        role="img"
        aria-labelledby={`${id}-title`}
        aria-describedby={`${id}-help`}
        tabIndex={0}
        onKeyDown={onKey}
        onBlur={() => setHover(null)}
        onPointerMove={(e) => setHover(nearest(e.clientX))}
        onPointerLeave={() => setHover(null)}
        onClick={() => hover !== null && onSelect?.(hover)}
        style={{ cursor: onSelect ? "pointer" : "default" }}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line className="gridline" x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} />
            <text className="tick" x={pad.left - 6} y={y(t) + 4} textAnchor="end">
              {format(t)}
            </text>
          </g>
        ))}
        <line className="baseline" x1={pad.left} x2={width - pad.right} y1={y(0)} y2={y(0)} />
        {points.length > 0 && (
          <>
            <text className="tick" x={x(0)} y={height - 8} textAnchor="start">
              {points[0]!.label}
            </text>
            {last > 0 && (
              <text className="tick" x={x(last)} y={height - 8} textAnchor="end">
                {points[last]!.label}
              </text>
            )}
          </>
        )}
        {hover !== null && (
          <line className="baseline" x1={x(hover)} x2={x(hover)} y1={pad.top} y2={pad.top + plotH} />
        )}
        {series.map((s, si) => (
          <g key={s.name}>
            <path d={paths[si]} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" />
            {points.map((p, i) => {
              const v = p.values[si];
              if (v === null || v === undefined) return null;
              const emphasised = i === hover || points.length <= 12;
              return emphasised ? (
                <circle
                  key={i}
                  className="mark"
                  cx={x(i)}
                  cy={y(v)}
                  r={i === hover ? 5 : 4}
                  fill={s.color}
                  stroke="var(--surface)"
                  strokeWidth={2}
                />
              ) : null;
            })}
          </g>
        ))}
      </svg>
      <p id={`${id}-help`} className="sr-only">
        Use the left and right arrow keys to move between points
        {onSelect ? " and Enter to open the selected run" : ""}. The same data is in the table.
      </p>
      <Tooltip state={tip} />
    </figure>
  );
}
