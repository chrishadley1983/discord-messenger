"use client";

import { useState, useEffect, useCallback, useRef } from "react";

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
  const popupRef = useRef<HTMLDivElement>(null);

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

  // Close popup when clicking outside
  useEffect(() => {
    if (!showForecast) return;
    const handleClick = (e: MouseEvent) => {
      if (popupRef.current && !popupRef.current.contains(e.target as Node)) {
        setShowForecast(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showForecast]);

  const hours = now.getHours().toString().padStart(2, "0");
  const minutes = now.getMinutes().toString().padStart(2, "0");
  const seconds = now.getSeconds().toString().padStart(2, "0");
  const dayStr = now.toLocaleDateString("en-GB", { weekday: "long" });
  const dateStr = now.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  const w = weather || {
    temp: "--",
    feelsLike: "--",
    rainChance: "--",
    icon: "⛅",
    description: "",
    location: "Tonbridge",
    hourly: [],
    daily: [],
  };

  return (
    <div className="flex items-center justify-between px-6 py-3 border-b border-border bg-surface shrink-0">
      {/* Clock + Title */}
      <div className="flex items-center gap-5">
        <div className="flex items-baseline gap-1.5">
          <span className="font-serif text-[54px] leading-none tracking-tight font-extralight">
            {hours}
            <span
              className="opacity-40"
              style={{ animation: "blink 1s step-end infinite" }}
            >
              :
            </span>
            {minutes}
          </span>
          <span className="text-base text-text-mid font-light ml-1">
            {seconds}
          </span>
        </div>
        <div className="font-serif text-[28px] font-extralight text-accent tracking-wide">
          Hadley Dashboard
        </div>
      </div>

      {/* Date */}
      <div className="text-center">
        <div className="text-base font-semibold">{dayStr}</div>
        <div className="text-xs text-text-mid mt-0.5">{dateStr}</div>
      </div>

      {/* Weather (pressable) */}
      <div className="relative" ref={popupRef}>
        <button
          onClick={() => { setShowForecast((v) => !v); setSelectedDay(null); }}
          className="flex items-center gap-2.5 cursor-pointer bg-transparent border-none p-2 -m-2 rounded-xl transition-colors hover:bg-surface-alt active:scale-[0.98]"
        >
          <span className="text-3xl">{w.icon}</span>
          <div className="text-left">
            <div className="flex items-baseline gap-1">
              <span className="font-serif text-[38px] leading-none font-extralight">
                {w.temp}°
              </span>
              <span className="text-sm text-text-mid">C</span>
            </div>
            <div className="text-sm text-text-mid mt-0.5">
              {w.location} · Feels {w.feelsLike}° · {w.rainChance}% rain
            </div>
          </div>
        </button>

        {/* Forecast popup */}
        {showForecast && weather && (
          <div className="absolute top-full right-0 mt-2 w-[720px] bg-surface border border-border rounded-2xl shadow-lg z-50 overflow-hidden">
            {/* Hourly strip */}
            <div className="p-6 border-b border-border">
              <div className="text-xs font-bold uppercase tracking-widest text-text-mid mb-4">
                {selectedDay !== null
                  ? `${weather.daily[selectedDay]?.dayName} — Hourly`
                  : "Today — Hourly"}
              </div>
              <div className="flex gap-1.5 overflow-x-auto">
                {(selectedDay !== null
                  ? weather.daily[selectedDay]?.hourly || []
                  : weather.hourly
                ).map((h, i) => (
                  <div
                    key={i}
                    className="flex flex-col items-center gap-1.5 min-w-[56px] py-3 px-2 rounded-xl bg-surface-alt"
                  >
                    <span className="text-xs text-text-mid font-medium">
                      {h.hour}
                    </span>
                    <span className="text-2xl">{h.icon}</span>
                    <span className="text-sm font-semibold">{h.temp}°</span>
                    {h.rainChance > 0 && (
                      <span className="text-sm text-blue font-medium">
                        {h.rainChance}%
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Daily forecast */}
            <div className="p-6">
              <div className="text-xs font-bold uppercase tracking-widest text-text-mid mb-4">
                Next 5 Days
              </div>
              <div className="flex flex-col gap-3">
                {weather.daily.map((d, i) => (
                  <button
                    key={i}
                    onClick={() => setSelectedDay(selectedDay === i ? null : i)}
                    className={`flex items-center gap-4 py-2.5 px-3 rounded-xl transition-colors cursor-pointer border-none w-full text-left ${
                      selectedDay === i
                        ? "bg-accent-glow ring-1 ring-accent/30"
                        : "bg-transparent hover:bg-surface-alt"
                    }`}
                  >
                    <span className="text-sm font-semibold w-12">
                      {i === 0 ? "Today" : d.dayName}
                    </span>
                    <span className="text-2xl">{d.icon}</span>
                    <span className="text-sm text-text-mid flex-1">
                      {d.desc}
                    </span>
                    {d.rainChance > 0 && (
                      <span className="text-xs text-blue font-medium w-10 text-right">
                        {d.rainChance}%
                      </span>
                    )}
                    <div className="flex items-center gap-2 w-20 justify-end">
                      <span className="text-sm font-semibold">{d.high}°</span>
                      <span className="text-xs text-text-dim">
                        {d.low}°
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
