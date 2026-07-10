"use client";

/**
 * Rest-state clock (DESIGN_SPEC_V2 §8 — screensaver).
 * Time-dominant luminous clock on deep night ink, with date + live weather.
 * Shows when screen-control reports "dim" (or legacy "off").
 * Whole surface is a wake target.
 */

import { useState, useEffect, useCallback, useRef } from "react";

interface ScreenState {
  state: "active" | "dim" | "off";
  idle_seconds: number;
  night_mode: boolean;
  mqtt_connected: boolean;
}

interface RestWeather {
  icon: string;
  temp: number;
  high: number | null;
  low: number | null;
  rain: number | null;
}

export default function ScreenOverlay() {
  const [screen, setScreen] = useState<ScreenState | null>(null);
  const [time, setTime] = useState("");
  const [date, setDate] = useState("");
  const [weather, setWeather] = useState<RestWeather | null>(null);
  const lastWakeRef = useRef(0);

  // Send wake on any user interaction (throttled to once per 30s)
  const sendWake = useCallback(() => {
    const now = Date.now();
    if (now - lastWakeRef.current < 30000) return;
    lastWakeRef.current = now;
    fetch("/api/screen/wake", { method: "POST" }).catch(() => {});
  }, []);

  // Listen for any touch/click/pointer activity on the whole page
  useEffect(() => {
    const handler = () => sendWake();
    document.addEventListener("pointerdown", handler, { passive: true });
    document.addEventListener("touchstart", handler, { passive: true });
    return () => {
      document.removeEventListener("pointerdown", handler);
      document.removeEventListener("touchstart", handler);
    };
  }, [sendWake]);

  const fetchScreen = useCallback(async () => {
    try {
      const res = await fetch("/api/screen");
      if (res.ok) setScreen(await res.json());
    } catch {
      // keep last state
    }
  }, []);

  // Poll screen state every 2s
  useEffect(() => {
    fetchScreen();
    const t = setInterval(fetchScreen, 2000);
    return () => clearInterval(t);
  }, [fetchScreen]);

  // Liveness heartbeat — proves this page's JS is still running. The kiosk
  // watchdog treats a stale heartbeat as a wedged renderer (frame looks fine
  // but JS/network is frozen) and kills/reloads the tab, so this must keep
  // beating in every screen state, not just while resting.
  useEffect(() => {
    const beat = () =>
      fetch("/api/screen/heartbeat", { method: "POST" }).catch(() => {});
    beat();
    const t = setInterval(beat, 20000);
    return () => clearInterval(t);
  }, []);

  const resting = screen?.state === "dim" || screen?.state === "off";

  // Clock tick
  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setTime(
        now.toLocaleTimeString("en-GB", {
          hour: "2-digit",
          minute: "2-digit",
          timeZone: "Europe/London",
        })
      );
      setDate(
        now.toLocaleDateString("en-GB", {
          weekday: "long",
          day: "numeric",
          month: "long",
          timeZone: "Europe/London",
        })
      );
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, []);

  // Weather while resting — refresh every 10 min
  useEffect(() => {
    if (!resting) return;
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch("/api/weather");
        if (!res.ok) return;
        const w = await res.json();
        if (cancelled) return;
        setWeather({
          icon: w.icon ?? "🌡️",
          temp: Math.round(w.temp ?? 0),
          high: w.daily?.[0]?.high ?? null,
          low: w.daily?.[0]?.low ?? null,
          rain: w.rainChance ?? null,
        });
      } catch {
        // keep last weather
      }
    };
    load();
    const t = setInterval(load, 10 * 60 * 1000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [resting]);

  if (!resting) return null;

  const [hh, mm] = time ? time.split(":") : ["", ""];

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        background: "var(--night-bg)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        cursor: "none",
        overflow: "hidden",
      }}
      onClick={() => {
        // Touch to wake — tell controller we have activity
        fetch("/api/screen/wake", { method: "POST" }).catch(() => {});
      }}
    >
      {/* Soft luminous halo behind the time */}
      <div
        aria-hidden
        style={{
          position: "absolute",
          width: 720,
          height: 380,
          borderRadius: "50%",
          background:
            "radial-gradient(ellipse at center, rgba(255,183,3,0.16) 0%, rgba(251,86,7,0.07) 45%, transparent 70%)",
          transform: "translateY(-40px)",
        }}
      />

      {/* TIME — dominant (~250px tall) */}
      <div
        style={{
          position: "relative",
          fontFamily: "var(--font-display), sans-serif",
          fontWeight: 300,
          fontSize: "16.5rem",
          lineHeight: 0.95,
          letterSpacing: "-0.03em",
          fontVariantNumeric: "tabular-nums",
          background:
            "linear-gradient(135deg, #FFB703 0%, #FFD54F 45%, #FB5607 130%)",
          WebkitBackgroundClip: "text",
          backgroundClip: "text",
          color: "transparent",
        }}
      >
        {hh}
        <span
          style={{
            // Explicit colour: background-clip:text on the parent doesn't
            // reliably paint through an opacity-animated child span
            background: "none",
            WebkitBackgroundClip: "initial",
            backgroundClip: "initial",
            color: "#FFC53D",
            animation: "blink 2s step-end infinite",
          }}
        >
          :
        </span>
        {mm}
      </div>

      {/* DATE */}
      <div
        style={{
          position: "relative",
          marginTop: "1.2rem",
          fontFamily: "var(--font-body), sans-serif",
          fontWeight: 600,
          fontSize: "1.6rem",
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          color: "rgba(255,255,255,0.6)",
        }}
      >
        {date}
      </div>

      {/* WEATHER */}
      {weather && (
        <div
          style={{
            position: "relative",
            marginTop: "1.6rem",
            display: "flex",
            alignItems: "center",
            gap: "1.1rem",
            padding: "0.7rem 1.6rem",
            borderRadius: 999,
            border: "1px solid rgba(255,255,255,0.14)",
            background: "rgba(255,255,255,0.05)",
          }}
        >
          <span style={{ fontSize: "2rem", lineHeight: 1 }}>{weather.icon}</span>
          <span
            style={{
              fontFamily: "var(--font-display), sans-serif",
              fontWeight: 600,
              fontSize: "1.9rem",
              color: "rgba(255,255,255,0.92)",
            }}
          >
            {weather.temp}°
          </span>
          {weather.high != null && weather.low != null && (
            <span
              style={{
                fontFamily: "var(--font-body), sans-serif",
                fontWeight: 600,
                fontSize: "1.1rem",
                color: "rgba(255,255,255,0.45)",
              }}
            >
              H {Math.round(weather.high)}°&nbsp;&nbsp;L {Math.round(weather.low)}°
            </span>
          )}
          {weather.rain != null && weather.rain > 10 && (
            <span
              style={{
                fontFamily: "var(--font-body), sans-serif",
                fontWeight: 600,
                fontSize: "1.1rem",
                color: "rgba(140,190,255,0.75)",
              }}
            >
              💧 {Math.round(weather.rain)}%
            </span>
          )}
        </div>
      )}
    </div>
  );
}
