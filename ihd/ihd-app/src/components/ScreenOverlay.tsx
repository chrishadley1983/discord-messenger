"use client";

import { useState, useEffect, useCallback, useRef } from "react";

interface ScreenState {
  state: "active" | "dim" | "off";
  idle_seconds: number;
  night_mode: boolean;
  mqtt_connected: boolean;
}

export default function ScreenOverlay() {
  const [screen, setScreen] = useState<ScreenState | null>(null);
  const [time, setTime] = useState("");
  const [date, setDate] = useState("");
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

  // Update clock every second
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

  const isDim = screen?.state === "dim";
  const isOff = screen?.state === "off";

  if (!isDim && !isOff) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        background: "#000",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        cursor: "none",
      }}
      onClick={() => {
        // Touch to wake — tell controller we have motion
        fetch("/api/screen/wake", { method: "POST" }).catch(() => {});
      }}
    >
      {isDim && (
        <>
          <div
            style={{
              fontFamily: "var(--font-fraunces), serif",
              fontSize: "10rem",
              fontWeight: 200,
              color: "rgba(255, 255, 255, 0.35)",
              lineHeight: 1,
              letterSpacing: "-0.02em",
            }}
          >
            {time}
          </div>
          <div
            style={{
              fontFamily: "var(--font-figtree), sans-serif",
              fontSize: "1.5rem",
              fontWeight: 300,
              color: "rgba(255, 255, 255, 0.15)",
              marginTop: "1rem",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
            }}
          >
            {date}
          </div>
        </>
      )}
    </div>
  );
}
