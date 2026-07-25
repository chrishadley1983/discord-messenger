"use client";

import { useState, useEffect, useCallback } from "react";
import SensorHistoryPopup from "./SensorHistoryPopup";
import { Card } from "../ui/Card";
import Icon from "../ui/Icon";

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

const SENSOR_CONFIG: { key: string; label: string }[] = [
  { key: "sensor_kitchen", label: "Kitchen" },
  { key: "sensor_bedroom", label: "Bedroom" },
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
      <Card
        section="calendar"
        chip="Sensors"
        chipIcon={<Icon name="thermometer" size={16} />}
        onClick={() => setShowHistory(true)}
        headerRight={<span className="text-[13px] font-semibold text-ink/40">History ▸</span>}
      >
        <div className="grid grid-cols-2 gap-2">
          {SENSOR_CONFIG.map((cfg) => {
            const s = !offline ? data.sensors[cfg.key] : null;
            return (
              <div
                key={cfg.key}
                className="text-center py-2 px-2 rounded-xl"
                style={{ background: "var(--surface-alt)" }}
              >
                <div className="text-[13px] font-bold uppercase text-ink/50 tracking-wide mb-1">
                  {cfg.label}
                </div>
                <div
                  className="font-bold"
                  style={{ fontFamily: "var(--font-display), sans-serif", fontSize: 26, color: "var(--ink)" }}
                >
                  {s?.temperature ?? "--"}
                  <span className="text-base">°C</span>
                </div>
                <div className="text-sm text-ink/60 mt-0.5">
                  {s?.humidity ?? "--"}% humidity
                </div>
              </div>
            );
          })}
        </div>

        {/* Motion indicator */}
        {motion && (
          <div className="mt-2 flex items-center gap-1.5 px-1 text-sm text-ink/60">
            <span
              className="w-2.5 h-2.5 rounded-full inline-block"
              style={{ background: motion.occupancy ? "var(--good)" : "var(--ink-12)" }}
            />
            Lounge {motion.occupancy ? "motion detected" : "clear"}
            {motion.illuminance != null && (
              <span className="ml-auto text-ink/40">{Math.round(motion.illuminance)} lux</span>
            )}
          </div>
        )}
      </Card>

      {showHistory && <SensorHistoryPopup onClose={() => setShowHistory(false)} />}
    </>
  );
}
