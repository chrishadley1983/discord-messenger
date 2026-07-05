"use client";

import { useState, useEffect, useCallback } from "react";
import Takeover from "../ui/Takeover";

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
      <div className="flex items-center justify-center text-ink/40 text-sm" style={{ height }}>
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
        <span className="text-sm font-semibold text-ink/60">{label}</span>
        <span className="text-base font-bold" style={{ color }}>
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
              <line x1={pad} y1={y} x2={width - pad} y2={y} stroke="rgba(34,26,58,0.08)" strokeWidth="1" />
              <text x={pad - 4} y={y + 3} textAnchor="end" fontSize="10" fill="rgba(34,26,58,0.35)">
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
      <div className="flex items-center justify-center text-ink/40 text-sm py-4">
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
        <span className="text-sm font-semibold text-ink/60">Motion (Lounge)</span>
        <span className="text-sm text-ink/40">{totalEvents} events</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ height: `${height}px` }}>
        {/* Background */}
        <rect x={pad} y={8} width={width - pad * 2} height={height - 16} rx={4} fill="rgba(34,26,58,0.04)" />
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
    <Takeover
      onClose={onClose}
      accent="var(--calendar)"
      title="Sensor History"
      actions={
        <div className="flex gap-1.5 rounded-xl p-1" style={{ background: "rgba(255,255,255,0.2)" }}>
          {(Object.entries(RANGE_LABELS) as [TimeRange, string][]).map(([val, label]) => (
            <button
              key={val}
              onClick={() => setRange(val)}
              className="pressable px-3 rounded-lg text-sm font-bold cursor-pointer border-2"
              style={{
                minHeight: 56,
                background: range === val ? "#fff" : "transparent",
                color: range === val ? "var(--calendar)" : "#fff",
                borderColor: range === val ? "#fff" : "rgba(255,255,255,0.4)",
              }}
            >
              {label}
            </button>
          ))}
        </div>
      }
    >
      <div className="h-full overflow-y-auto p-5">
        {loading ? (
          <div className="flex items-center justify-center py-12 text-ink/50 text-base">
            Loading sensor data...
          </div>
        ) : (
          <div className="flex flex-col gap-5">
            {/* Battery row */}
            <div className="flex gap-4 flex-wrap">
              {[
                { label: "Kitchen", battery: latestKitchen?.battery, color: COLORS.kitchen },
                { label: "Bedroom", battery: latestBedroom?.battery, color: COLORS.bedroom },
                { label: "Motion", battery: latestMotion?.battery, color: COLORS.motion },
              ].map((b) => (
                <div key={b.label} className="flex items-center gap-1.5 text-sm text-ink/60">
                  <span
                    className="w-2.5 h-2.5 rounded-full inline-block"
                    style={{ background: b.color }}
                  />
                  {b.label}:
                  <span className="font-semibold" style={{ color: (b.battery ?? 0) < 20 ? "var(--bad)" : "inherit" }}>
                    {b.battery != null ? `${b.battery}%` : "--"}
                  </span>
                </div>
              ))}
            </div>

            {/* Temperature charts */}
            <div className="grid grid-cols-2 gap-4">
              <div className="rounded-2xl p-3" style={{ background: "var(--surface-alt)" }}>
                <MiniChart data={kitchenTemp} color={COLORS.kitchen} label="Kitchen Temp" unit="°C" />
              </div>
              <div className="rounded-2xl p-3" style={{ background: "var(--surface-alt)" }}>
                <MiniChart data={bedroomTemp} color={COLORS.bedroom} label="Bedroom Temp" unit="°C" />
              </div>
            </div>

            {/* Humidity charts */}
            <div className="grid grid-cols-2 gap-4">
              <div className="rounded-2xl p-3" style={{ background: "var(--surface-alt)" }}>
                <MiniChart data={kitchenHumid} color={COLORS.kitchen} label="Kitchen Humidity" unit="%" />
              </div>
              <div className="rounded-2xl p-3" style={{ background: "var(--surface-alt)" }}>
                <MiniChart data={bedroomHumid} color={COLORS.bedroom} label="Bedroom Humidity" unit="%" />
              </div>
            </div>

            {/* Motion timeline */}
            <div className="rounded-2xl p-3" style={{ background: "var(--surface-alt)" }}>
              <MotionTimeline events={motion} hours={Number(range)} />
            </div>
          </div>
        )}
      </div>
    </Takeover>
  );
}
