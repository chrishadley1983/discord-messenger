"use client";

/**
 * Control screen (DESIGN_SPEC_V2 §8, "Control `/control` (mint) — REAL SCREEN").
 * 2x2 grid of sticker control cards: Screen, Kitchen Plug, Media, Coming Soon.
 */

import { useEffect, useState, useCallback } from "react";
import DashboardShell from "@/components/DashboardShell";
import { Card } from "@/components/ui/Card";
import Icon from "@/components/ui/Icon";

/* ---------- shared bits ---------- */

type BadgeTone = "good" | "warn" | "bad" | "neutral";

function StatusBadge({ tone, children }: { tone: BadgeTone; children: React.ReactNode }) {
  const bg =
    tone === "good"
      ? "var(--good)"
      : tone === "warn"
        ? "var(--warn)"
        : tone === "bad"
          ? "var(--bad)"
          : "var(--ink-08)";
  const color = tone === "neutral" ? "var(--ink-60)" : "#fff";
  return (
    <span
      className="inline-flex items-center"
      style={{
        background: bg,
        color,
        fontFamily: "var(--font-display), sans-serif",
        fontWeight: 700,
        fontSize: 12,
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        padding: "4px 10px",
        borderRadius: 999,
        border: "2px solid var(--ink)",
      }}
    >
      {children}
    </span>
  );
}

function ActionButton({
  onClick,
  disabled,
  variant = "solid",
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  variant?: "solid" | "outline";
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="pressable cursor-pointer disabled:cursor-default disabled:opacity-50 w-full"
      style={{
        minHeight: 64,
        borderRadius: 16,
        border: "2px solid var(--ink)",
        background: variant === "solid" ? "var(--ink)" : "var(--surface)",
        color: variant === "solid" ? "#fff" : "var(--ink)",
        fontFamily: "var(--font-display), sans-serif",
        fontWeight: 700,
        fontSize: 15,
        boxShadow: "3px 3px 0 var(--ink-08)",
      }}
    >
      {children}
    </button>
  );
}

function humaniseIdle(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
}

/* ---------- Screen card ---------- */

interface ScreenState {
  state: string;
  idle_seconds: number;
  display_on: boolean;
  night_mode: boolean;
}

function ScreenCard() {
  const [data, setData] = useState<ScreenState | null>(null);
  const [waking, setWaking] = useState(false);
  const [woken, setWoken] = useState(false);

  const poll = useCallback(async () => {
    try {
      const res = await fetch("/api/screen", { cache: "no-store" });
      if (res.ok) setData(await res.json());
    } catch {
      // keep last-known state
    }
  }, []);

  useEffect(() => {
    poll();
    const t = setInterval(poll, 5000);
    return () => clearInterval(t);
  }, [poll]);

  const wake = async () => {
    setWaking(true);
    try {
      const res = await fetch("/api/screen/wake", { method: "POST" });
      if (res.ok) {
        setWoken(true);
        setTimeout(() => setWoken(false), 1800);
        poll();
      }
    } catch {
      // ignore
    } finally {
      setWaking(false);
    }
  };

  const isActive = data?.state === "active";
  const tone: BadgeTone = data ? (isActive ? "good" : "warn") : "neutral";
  const label = data ? (isActive ? "Active" : data.state === "dim" ? "Dim" : data.state) : "…";

  return (
    <Card section="control" chip="Screen" chipIcon={<Icon name="monitor" size={16} />} headerRight={<StatusBadge tone={tone}>{label}</StatusBadge>}>
      <div className="flex-1 flex flex-col justify-center gap-1 mb-4">
        <span className="text-sm" style={{ color: "var(--ink-60)" }}>
          Idle for
        </span>
        <span
          style={{
            fontFamily: "var(--font-display), sans-serif",
            fontWeight: 700,
            fontSize: 40,
            fontVariantNumeric: "tabular-nums",
            lineHeight: 1,
          }}
        >
          {data ? humaniseIdle(data.idle_seconds) : "—"}
        </span>
      </div>
      <ActionButton onClick={wake} disabled={waking}>
        <span className="inline-flex items-center gap-2">
          {!woken && <Icon name="sun" size={16} />}
          {woken ? "Woken ✓" : waking ? "Waking…" : "Wake screen"}
        </span>
      </ActionButton>
    </Card>
  );
}

/* ---------- Kitchen plug card ---------- */

interface PlugState {
  status: string;
  state: string | null;
  friendly_name?: string;
}

function PlugCard() {
  const [data, setData] = useState<PlugState | null>(null);
  const [toggling, setToggling] = useState(false);
  const [toggleError, setToggleError] = useState(false);

  const poll = useCallback(async () => {
    try {
      const res = await fetch("/api/plug", { cache: "no-store" });
      const json: PlugState = await res.json();
      setData(json);
    } catch {
      setData({ status: "offline", state: null });
    }
  }, []);

  useEffect(() => {
    poll();
    const t = setInterval(poll, 5000);
    return () => clearInterval(t);
  }, [poll]);

  const reachable = data?.status === "ok";
  const isOn = data?.state === "ON";

  const toggle = async () => {
    if (!reachable) return;
    setToggling(true);
    setToggleError(false);
    try {
      const res = await fetch("/api/plug", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state: isOn ? "OFF" : "ON" }),
      });
      const json = await res.json();
      if (!res.ok || json.status !== "ok") throw new Error("toggle failed");
      await poll();
    } catch {
      setToggleError(true);
      setTimeout(() => setToggleError(false), 2500);
    } finally {
      setToggling(false);
    }
  };

  const tone: BadgeTone = !data ? "neutral" : !reachable ? "bad" : isOn ? "good" : "neutral";
  const label = !data ? "…" : !reachable ? "OFFLINE" : isOn ? "On" : "Off";

  const handleAction = () => {
    if (!reachable) {
      poll();
      return;
    }
    toggle();
  };

  return (
    <Card section="control" chip="Kitchen Plug" chipIcon={<Icon name="plug" size={16} />} headerRight={<StatusBadge tone={tone}>{label}</StatusBadge>}>
      <div className="flex-1 flex flex-col justify-center gap-1 mb-4">
        <span className="text-sm" style={{ color: "var(--ink-60)" }}>
          {reachable ? data?.friendly_name || "Sonoff plug" : "Can't reach the Zigbee bridge — check the hub is powered"}
        </span>
        {toggleError && (
          <span className="text-xs font-semibold" style={{ color: "var(--bad)" }}>
            Toggle failed — try again
          </span>
        )}
      </div>
      <ActionButton onClick={handleAction} disabled={toggling}>
        {toggling ? "Switching…" : !reachable ? "Retry" : isOn ? "Turn off" : "Turn on"}
      </ActionButton>
    </Card>
  );
}

/* ---------- Media card ---------- */

function MediaCard() {
  const [closing, setClosing] = useState(false);
  const [closed, setClosed] = useState(false);

  const close = async () => {
    setClosing(true);
    try {
      await fetch("/api/media", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "close" }),
      });
      setClosed(true);
      setTimeout(() => setClosed(false), 1800);
    } catch {
      // ignore
    } finally {
      setClosing(false);
    }
  };

  return (
    <Card section="control" chip="Media" chipIcon={<Icon name="tv" size={16} />}>
      <div className="flex-1 flex flex-col justify-center gap-1 mb-4">
        <span className="text-sm" style={{ color: "var(--ink-60)" }}>
          Stops Netflix, YouTube or Now TV playback on the lounge TV
        </span>
      </div>
      <ActionButton onClick={close} disabled={closing}>
        <span className="inline-flex items-center gap-2">
          {!closed && <Icon name="stop" size={16} />}
          {closed ? "Closed ✓" : closing ? "Closing…" : "Close running app"}
        </span>
      </ActionButton>
    </Card>
  );
}

/* ---------- Coming soon card ---------- */

function ComingSoonCard() {
  return (
    <Card
      section="control"
      chip="Coming Soon"
      chipIcon={<Icon name="sparkle" size={16} />}
      headerRight={
        <span
          className="inline-block"
          style={{
            background: "var(--control)",
            color: "var(--ink)",
            fontFamily: "var(--font-display), sans-serif",
            fontWeight: 800,
            fontSize: 12,
            letterSpacing: "0.08em",
            padding: "4px 12px",
            borderRadius: 999,
            border: "2px solid var(--ink)",
            transform: "rotate(-1.5deg)",
          }}
        >
          SOON
        </span>
      }
    >
      <div className="flex-1 flex items-center">
        <span className="text-base font-semibold" style={{ color: "var(--ink-30)" }}>
          Lights · Heating
        </span>
      </div>
    </Card>
  );
}

/* ---------- Page ---------- */

export default function ControlPage() {
  return (
    <DashboardShell>
      <div className="h-full flex flex-col justify-center py-4">
        <div className="grid grid-cols-2 grid-rows-2 gap-5 stagger-in" style={{ height: "100%", maxHeight: 560 }}>
          <ScreenCard />
          <PlugCard />
          <MediaCard />
          <ComingSoonCard />
        </div>
      </div>
    </DashboardShell>
  );
}
