"use client";

import { useState, useEffect, useCallback } from "react";

interface Reading {
  ts: string;
  device: string;
  temperature: number;
  humidity: number;
  battery: number;
}

interface MotionEvent {
  ts: string;
  device: string;
  occupancy: number;
  illuminance: number;
  battery: number;
}

type TimeRange = "24" | "168" | "720";

const RANGE_LABELS: Record<TimeRange, string> = {
  "24": "24h",
  "168": "7 days",
  "720": "30 days",
};

const COLORS = {
  kitchen: "#c47f0a",
  bedroom: "#3b82f6",
  motion: "#8b5cf6",
};

// ── SVG Line Chart ──────────────────────────────────────────────────

function MiniChart({
  data,
  color,
  width = 500,
  height = 120,
  unit,
  label,
}: {
  data: { ts: number; value: number }[];
  color: string;
  width?: number;
  height?: number;
  unit: string;
  label: string;
}) {
  if (data.length < 2) {
    return (
      <div className="flex items-center justify-center text-text-dim text-xs" style={{ height }}>
        Not enough data yet for {label}
      </div>
    );
  }

  const values = data.map((d) => d.value);
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const range = maxV - minV || 1;
  const pad = 16;

  const minT = data[0].ts;
  const maxT = data[data.length - 1].ts;
  const tRange = maxT - minT || 1;

  const points = data.map((d) => {
    const x = pad + ((d.ts - minT) / tRange) * (width - pad * 2);
    const y = height - pad - ((d.value - minV) / range) * (height - pad * 2);
    return `${x},${y}`;
  });

  const latest = values[values.length - 1];

  return (
    <div>
      <div className="flex justify-between items-baseline mb-1">
        <span className="text-xs font-semibold text-text-mid">{label}</span>
        <span className="text-sm font-bold" style={{ color }}>
          {latest.toFixed(1)}{unit}
        </span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ height: `${height}px` }}>
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((f) => {
          const y = height - pad - f * (height - pad * 2);
          const val = minV + f * range;
          return (
            <g key={f}>
              <line x1={pad} y1={y} x2={width - pad} y2={y} stroke="rgba(0,0,0,0.06)" strokeWidth="1" />
              <text x={pad - 4} y={y + 3} textAnchor="end" fontSize="8" fill="rgba(0,0,0,0.3)">
                {val.toFixed(1)}
              </text>
            </g>
          );
        })}
        {/* Line */}
        <polyline
          points={points.join(" ")}
          fill="none"
          stroke={color}
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {/* Area fill */}
        <polygon
          points={`${pad},${height - pad} ${points.join(" ")} ${width - pad},${height - pad}`}
          fill={color}
          opacity="0.08"
        />
      </svg>
    </div>
  );
}

// ── Motion Timeline ─────────────────────────────────────────────────

function MotionTimeline({ events, hours }: { events: MotionEvent[]; hours: number }) {
  if (events.length === 0) {
    return (
      <div className="flex items-center justify-center text-text-dim text-xs py-4">
        No motion events recorded yet
      </div>
    );
  }

  const now = Date.now();
  const start = now - hours * 60 * 60 * 1000;
  const width = 500;
  const height = 40;
  const pad = 16;

  // Only occupancy=true events
  const active = events.filter((e) => e.occupancy === 1);
  const totalEvents = active.length;

  return (
    <div>
      <div className="flex justify-between items-baseline mb-1">
        <span className="text-xs font-semibold text-text-mid">Motion (Lounge)</span>
        <span className="text-xs text-text-dim">{totalEvents} events</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ height: `${height}px` }}>
        {/* Background */}
        <rect x={pad} y={8} width={width - pad * 2} height={height - 16} rx={4} fill="rgba(0,0,0,0.03)" />
        {/* Event dots */}
        {active.map((e, i) => {
          const t = new Date(e.ts).getTime();
          const x = pad + ((t - start) / (now - start)) * (width - pad * 2);
          if (x < pad || x > width - pad) return null;
          return (
            <circle key={i} cx={x} cy={height / 2} r={3} fill={COLORS.motion} opacity={0.7} />
          );
        })}
      </svg>
    </div>
  );
}

// ── Main Popup ──────────────────────────────────────────────────────

export default function SensorHistoryPopup({ onClose }: { onClose: () => void }) {
  const [range, setRange] = useState<TimeRange>("24");
  const [readings, setReadings] = useState<Reading[]>([]);
  const [motion, setMotion] = useState<MotionEvent[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [readRes, motionRes] = await Promise.all([
        fetch(`/api/sensor/history?hours=${range}`),
        fetch(`/api/sensor/history?hours=${range}&type=motion`),
      ]);
      if (readRes.ok) setReadings(await readRes.json());
      if (motionRes.ok) setMotion(await motionRes.json());
    } catch {
      /* keep last */
    }
    setLoading(false);
  }, [range]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Split readings by device
  const kitchenTemp = readings
    .filter((r) => r.device === "sensor_kitchen" && r.temperature != null)
    .map((r) => ({ ts: new Date(r.ts).getTime(), value: r.temperature }));

  const bedroomTemp = readings
    .filter((r) => r.device === "sensor_bedroom" && r.temperature != null)
    .map((r) => ({ ts: new Date(r.ts).getTime(), value: r.temperature }));

  const kitchenHumid = readings
    .filter((r) => r.device === "sensor_kitchen" && r.humidity != null)
    .map((r) => ({ ts: new Date(r.ts).getTime(), value: r.humidity }));

  const bedroomHumid = readings
    .filter((r) => r.device === "sensor_bedroom" && r.humidity != null)
    .map((r) => ({ ts: new Date(r.ts).getTime(), value: r.humidity }));

  // Battery levels (latest per device)
  const latestKitchen = readings.filter((r) => r.device === "sensor_kitchen").slice(-1)[0];
  const latestBedroom = readings.filter((r) => r.device === "sensor_bedroom").slice(-1)[0];
  const latestMotion = motion.slice(-1)[0];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.5)" }}
      onClick={onClose}
    >
      <div
        className="bg-surface rounded-3xl shadow-xl w-[90vw] max-w-[1200px] max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 pb-3 border-b border-border">
          <h2 className="text-lg font-semibold text-text-main">Sensor History</h2>
          <div className="flex items-center gap-3">
            {/* Range toggle */}
            <div className="flex gap-1 bg-surface-alt rounded-xl p-1">
              {(Object.entries(RANGE_LABELS) as [TimeRange, string][]).map(([val, label]) => (
                <button
                  key={val}
                  onClick={() => setRange(val)}
                  className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-all"
                  style={{
                    background: range === val ? "var(--accent)" : "transparent",
                    color: range === val ? "white" : "var(--text-mid)",
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
            <button
              onClick={onClose}
              className="w-9 h-9 rounded-full flex items-center justify-center text-text-dim text-lg"
              style={{ background: "rgba(0,0,0,0.05)" }}
            >
              {"\u2715"}
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5">
          {loading ? (
            <div className="flex items-center justify-center py-12 text-text-dim">
              Loading sensor data...
            </div>
          ) : (
            <div className="space-y-5">
              {/* Battery row */}
              <div className="flex gap-4">
                {[
                  { label: "Kitchen", battery: latestKitchen?.battery, color: COLORS.kitchen },
                  { label: "Bedroom", battery: latestBedroom?.battery, color: COLORS.bedroom },
                  { label: "Motion", battery: latestMotion?.battery, color: COLORS.motion },
                ].map((b) => (
                  <div key={b.label} className="flex items-center gap-1.5 text-xs text-text-mid">
                    <span
                      className="w-2 h-2 rounded-full inline-block"
                      style={{ background: b.color }}
                    />
                    {b.label}:
                    <span className="font-semibold" style={{ color: (b.battery ?? 0) < 20 ? "#DC2626" : "inherit" }}>
                      {b.battery != null ? `${b.battery}%` : "--"}
                    </span>
                  </div>
                ))}
              </div>

              {/* Temperature charts */}
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-surface-alt rounded-2xl p-3">
                  <MiniChart data={kitchenTemp} color={COLORS.kitchen} label="Kitchen Temp" unit={"\u00B0C"} />
                </div>
                <div className="bg-surface-alt rounded-2xl p-3">
                  <MiniChart data={bedroomTemp} color={COLORS.bedroom} label="Bedroom Temp" unit={"\u00B0C"} />
                </div>
              </div>

              {/* Humidity charts */}
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-surface-alt rounded-2xl p-3">
                  <MiniChart data={kitchenHumid} color={COLORS.kitchen} label="Kitchen Humidity" unit="%" />
                </div>
                <div className="bg-surface-alt rounded-2xl p-3">
                  <MiniChart data={bedroomHumid} color={COLORS.bedroom} label="Bedroom Humidity" unit="%" />
                </div>
              </div>

              {/* Motion timeline */}
              <div className="bg-surface-alt rounded-2xl p-3">
                <MotionTimeline events={motion} hours={Number(range)} />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
