"use client";

/**
 * Slim shell header (DESIGN_SPEC_V2 §5): big display-font clock, title,
 * date, weather chip. Forecast opens in a CENTRED Modal (fixes the old
 * right-edge-overflow popover).
 */

import { useState, useEffect, useCallback } from "react";
import Modal from "@/components/ui/Modal";

interface HourlyForecast {
  hour: string;
  temp: number;
  icon: string;
  rainChance: number;
}

interface DailyForecast {
  date: string;
  dayName: string;
  high: number;
  low: number;
  icon: string;
  desc: string;
  rainChance: number;
  hourly: HourlyForecast[];
}

interface WeatherData {
  temp: number;
  feelsLike: number;
  rainChance: number;
  icon: string;
  description: string;
  location: string;
  hourly: HourlyForecast[];
  daily: DailyForecast[];
}

export default function Header() {
  const [now, setNow] = useState(new Date());
  const [weather, setWeather] = useState<WeatherData | null>(null);
  const [showForecast, setShowForecast] = useState(false);
  const [selectedDay, setSelectedDay] = useState<number | null>(null);

  const fetchWeather = useCallback(async () => {
    try {
      const res = await fetch("/api/weather");
      if (res.ok) {
        setWeather(await res.json());
      }
    } catch {
      // keep showing last known weather or fallback
    }
  }, []);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    fetchWeather();
    const t = setInterval(fetchWeather, 10 * 60 * 1000);
    return () => clearInterval(t);
  }, [fetchWeather]);

  const hours = now.getHours().toString().padStart(2, "0");
  const minutes = now.getMinutes().toString().padStart(2, "0");
  const dayStr = now.toLocaleDateString("en-GB", { weekday: "long" });
  const dateStr = now.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
  });

  const w = weather || {
    temp: "--" as unknown as number,
    feelsLike: "--" as unknown as number,
    rainChance: "--" as unknown as number,
    icon: "⛅",
    description: "",
    location: "Tonbridge",
    hourly: [],
    daily: [],
  };

  return (
    <div
      className="flex items-center justify-between pl-6 pr-4 py-2 shrink-0"
      style={{ background: "var(--surface)", borderBottom: "2px solid var(--ink)" }}
    >
      {/* Clock + Title */}
      <div className="flex items-center gap-5">
        <span
          className="leading-none"
          style={{
            fontFamily: "var(--font-display), sans-serif",
            fontWeight: 600,
            fontSize: 46,
            letterSpacing: "-0.02em",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {hours}
          <span className="opacity-50" style={{ animation: "blink 2s step-end infinite" }}>
            :
          </span>
          {minutes}
        </span>
        <div className="flex flex-col leading-tight">
          <span
            style={{
              fontFamily: "var(--font-display), sans-serif",
              fontWeight: 800,
              fontSize: 22,
              letterSpacing: "-0.01em",
            }}
          >
            Hadley&nbsp;HQ
          </span>
          <span className="text-sm" style={{ color: "var(--text-mid)" }}>
            {dayStr} {dateStr}
          </span>
        </div>
      </div>

      {/* Weather chip (opens centred modal) */}
      <button
        onClick={() => {
          setShowForecast(true);
          setSelectedDay(null);
        }}
        className="pressable flex items-center gap-3 cursor-pointer"
        style={{
          border: "2px solid var(--ink)",
          borderRadius: 18,
          background: "var(--surface)",
          padding: "6px 16px",
          minHeight: 56,
          boxShadow: "3px 3px 0 var(--ink-08)",
        }}
      >
        <span className="text-3xl leading-none">{w.icon}</span>
        <div className="text-left">
          <div className="flex items-baseline gap-1">
            <span
              className="leading-none"
              style={{
                fontFamily: "var(--font-display), sans-serif",
                fontWeight: 700,
                fontSize: 32,
              }}
            >
              {w.temp}°
            </span>
          </div>
          <div className="text-xs" style={{ color: "var(--text-mid)" }}>
            Feels {w.feelsLike}° · {w.rainChance}% rain
          </div>
        </div>
      </button>

      {/* Forecast modal — centred, never clipped */}
      {showForecast && weather && (
        <Modal
          onClose={() => setShowForecast(false)}
          accent="var(--calendar)"
          title={`${weather.location} weather`}
          maxWidth={760}
        >
          {/* Hourly strip */}
          <div className="p-5" style={{ borderBottom: "2px solid var(--ink-12)" }}>
            <div
              className="mb-3 uppercase"
              style={{
                fontFamily: "var(--font-display), sans-serif",
                fontWeight: 700,
                fontSize: 13,
                letterSpacing: "0.08em",
                color: "var(--text-mid)",
              }}
            >
              {selectedDay !== null
                ? `${weather.daily[selectedDay]?.dayName} — Hourly`
                : "Today — Hourly"}
            </div>
            <div className="flex gap-1.5 overflow-x-auto pb-1">
              {(selectedDay !== null
                ? weather.daily[selectedDay]?.hourly || []
                : weather.hourly
              ).map((h, i) => (
                <div
                  key={i}
                  className="flex flex-col items-center gap-1 min-w-[60px] py-2.5 px-2"
                  style={{ background: "var(--surface-alt)", borderRadius: 14 }}
                >
                  <span className="text-xs font-medium" style={{ color: "var(--text-mid)" }}>
                    {h.hour}
                  </span>
                  <span className="text-2xl">{h.icon}</span>
                  <span className="text-sm font-bold">{h.temp}°</span>
                  {h.rainChance > 0 && (
                    <span className="text-xs font-semibold" style={{ color: "var(--calendar)" }}>
                      {h.rainChance}%
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Daily forecast */}
          <div className="p-5">
            <div
              className="mb-3 uppercase"
              style={{
                fontFamily: "var(--font-display), sans-serif",
                fontWeight: 700,
                fontSize: 13,
                letterSpacing: "0.08em",
                color: "var(--text-mid)",
              }}
            >
              Next 5 Days
            </div>
            <div className="flex flex-col gap-2">
              {weather.daily.map((d, i) => (
                <button
                  key={i}
                  onClick={() => setSelectedDay(selectedDay === i ? null : i)}
                  className="pressable flex items-center gap-4 w-full text-left cursor-pointer"
                  style={{
                    minHeight: 56,
                    padding: "8px 14px",
                    borderRadius: 14,
                    border: selectedDay === i ? "2px solid var(--ink)" : "2px solid transparent",
                    background: selectedDay === i ? "var(--calendar-tint)" : "transparent",
                  }}
                >
                  <span className="text-sm font-bold w-14">
                    {i === 0 ? "Today" : d.dayName}
                  </span>
                  <span className="text-2xl">{d.icon}</span>
                  <span className="text-sm flex-1" style={{ color: "var(--text-mid)" }}>
                    {d.desc}
                  </span>
                  {d.rainChance > 0 && (
                    <span
                      className="text-xs font-semibold w-10 text-right"
                      style={{ color: "var(--calendar)" }}
                    >
                      {d.rainChance}%
                    </span>
                  )}
                  <div className="flex items-center gap-2 w-20 justify-end">
                    <span className="text-sm font-bold">{d.high}°</span>
                    <span className="text-xs" style={{ color: "var(--text-dim)" }}>
                      {d.low}°
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
