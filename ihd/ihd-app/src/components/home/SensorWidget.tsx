"use client";

import { useState, useEffect, useCallback } from "react";
import SensorHistoryPopup from "./SensorHistoryPopup";

interface SensorReading {
  temperature: number | null;
  humidity: number | null;
  battery: number | null;
  occupancy?: boolean | null;
  illuminance?: number | null;
}

interface SensorResponse {
  status: string;
  sensors: Record<string, SensorReading>;
}

const SENSOR_CONFIG: { key: string; label: string; color: string }[] = [
  { key: "sensor_kitchen", label: "Kitchen", color: "var(--accent)" },
  { key: "sensor_bedroom", label: "Bedroom", color: "var(--blue)" },
];

export default function SensorWidget() {
  const [data, setData] = useState<SensorResponse | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  const fetchSensors = useCallback(async () => {
    try {
      const res = await fetch("/api/sensor");
      if (res.ok) setData(await res.json());
    } catch {
      // keep last known data
    }
  }, []);

  useEffect(() => {
    fetchSensors();
    const t = setInterval(fetchSensors, 30_000);
    return () => clearInterval(t);
  }, [fetchSensors]);

  const offline = !data || data.status === "offline";
  const motion = data?.sensors?.["motion_lounge"];

  return (
    <>
      <button
        onClick={() => setShowHistory(true)}
        className="bg-surface border border-border rounded-2xl p-3 shadow-sm flex flex-col w-full text-left cursor-pointer transition-all hover:shadow-md active:scale-[0.98]"
      >
        <div className="text-xs font-bold uppercase tracking-widest text-text-mid mb-2 flex items-center justify-between">
          <span>Sensors</span>
          <span className="text-text-dim font-normal normal-case tracking-normal text-[0.6rem]">
            tap for history {"\u25B8"}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {SENSOR_CONFIG.map((cfg) => {
            const s = !offline ? data.sensors[cfg.key] : null;
            return (
              <div
                key={cfg.key}
                className="text-center py-2 px-2 bg-surface-alt rounded-xl"
              >
                <div className="text-[0.65rem] font-bold uppercase text-text-dim tracking-wide mb-1">
                  {cfg.label}
                </div>
                <div
                  className="font-serif text-2xl font-extralight"
                  style={{ color: cfg.color }}
                >
                  {s?.temperature ?? "--"}
                  <span className="text-sm">{"\u00B0"}C</span>
                </div>
                <div className="text-xs text-text-mid mt-0.5">
                  {s?.humidity ?? "--"}% humidity
                </div>
              </div>
            );
          })}
        </div>

        {/* Motion indicator */}
        {motion && (
          <div className="mt-2 flex items-center gap-1.5 px-1 text-xs text-text-mid">
            <span
              className="w-2 h-2 rounded-full inline-block"
              style={{ background: motion.occupancy ? "#16A34A" : "rgba(0,0,0,0.15)" }}
            />
            Lounge {motion.occupancy ? "motion detected" : "clear"}
            {motion.illuminance != null && (
              <span className="ml-auto text-text-dim">{Math.round(motion.illuminance)} lux</span>
            )}
          </div>
        )}
      </button>

      {showHistory && <SensorHistoryPopup onClose={() => setShowHistory(false)} />}
    </>
  );
}
