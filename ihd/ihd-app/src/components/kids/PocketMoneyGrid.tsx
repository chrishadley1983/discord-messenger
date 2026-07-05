"use client";

import { useState, useEffect, useCallback, Fragment } from "react";
import Takeover from "../ui/Takeover";

const CATEGORIES = [
  { key: "room_tidy", label: "Room Tidy", emoji: "\u{1F6CF}️", rate: 40 },
  { key: "behaviour", label: "Behaviour", emoji: "⭐", rate: 20 },
  { key: "homework", label: "Homework", emoji: "\u{1F4DA}", rate: 20 },
  { key: "special_boost", label: "Boost", emoji: "\u{1F680}", rate: 200 },
] as const;

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

type Grid = Record<string, Record<string, boolean>>;

interface PocketMoneyGridProps {
  child: "emmie" | "max";
  onClose: () => void;
}

const CHILD_CONFIG = {
  emmie: { name: "Emmie", color: "var(--emmie)" },
  max: { name: "Max", color: "var(--max)" },
};

function formatPence(pence: number): string {
  return `£${(pence / 100).toFixed(2)}`;
}

export default function PocketMoneyGrid({ child, onClose }: PocketMoneyGridProps) {
  const [grid, setGrid] = useState<Grid | null>(null);

  // Which day index is today (0=Mon, 6=Sun)
  const todayIdx = (() => { const d = new Date().getDay(); return d === 0 ? 6 : d - 1; })();

  const fetchGrid = useCallback(async () => {
    try {
      const res = await fetch("/api/kids/pocket-money/grid");
      if (res.ok) {
        const data = await res.json();
        setGrid(data[child]);
      }
    } catch { /* ignore */ }
  }, [child]);

  useEffect(() => { fetchGrid(); }, [fetchGrid]);

  const toggle = async (category: string, day: string, currentValue: boolean) => {
    // Optimistic update
    setGrid((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        [category]: { ...prev[category], [day]: !currentValue },
      };
    });

    try {
      await fetch("/api/kids/pocket-money/grid", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ child, category, day, value: !currentValue }),
      });
    } catch { /* optimistic already applied */ }
  };

  const config = CHILD_CONFIG[child];

  // Count ticks + earnings for the footer summary
  const tickCount = grid
    ? CATEGORIES.reduce((sum, cat) => sum + DAYS.filter((d) => grid[cat.key]?.[d]).length, 0)
    : 0;
  const totalDays = CATEGORIES.length * 7;
  const earnedPence = grid
    ? CATEGORIES.reduce((sum, cat) => sum + cat.rate * DAYS.filter((d) => grid[cat.key]?.[d]).length, 0)
    : 0;

  return (
    <Takeover onClose={onClose} accent={config.color} title={`${config.name}'s Weekly Grid`}>
      <div className="h-full flex flex-col min-h-0">
        <div className="flex-1 min-h-0 overflow-y-auto p-6 flex items-start justify-center">
          {!grid ? (
            <div className="text-center text-lg py-12" style={{ color: "var(--ink-60)" }}>Loading...</div>
          ) : (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "170px repeat(7, 64px)",
                gridAutoRows: "min-content",
                gap: 10,
              }}
            >
              {/* Header row */}
              <div />
              {DAY_LABELS.map((label, i) => (
                <div
                  key={label}
                  className="flex flex-col items-center justify-center"
                  style={{
                    fontFamily: "var(--font-display), sans-serif",
                    fontWeight: 700,
                    fontSize: 16,
                    color: i === todayIdx ? config.color : "var(--ink-60)",
                  }}
                >
                  {label}
                  {i === todayIdx && (
                    <span
                      className="rounded-full mt-1"
                      style={{ width: 6, height: 6, background: config.color }}
                    />
                  )}
                </div>
              ))}

              {/* Category rows */}
              {CATEGORIES.map((cat) => (
                <Fragment key={cat.key}>
                  <div className="flex items-center gap-2" style={{ fontSize: 16, fontWeight: 700 }}>
                    <span className="text-2xl">{cat.emoji}</span>
                    {cat.label}
                  </div>
                  {DAYS.map((day, i) => {
                    const checked = grid[cat.key]?.[day] ?? false;
                    const isToday = i === todayIdx;
                    return (
                      <button
                        key={day}
                        onClick={() => toggle(cat.key, day, checked)}
                        aria-label={`${cat.label} — ${DAY_LABELS[i]}`}
                        className="pressable flex items-center justify-center rounded-2xl cursor-pointer"
                        style={{
                          width: 64,
                          height: 64,
                          background: checked ? config.color : "var(--surface)",
                          border: `2px solid ${isToday ? config.color : "var(--ink)"}`,
                          boxShadow: isToday
                            ? `0 0 0 3px ${config.color}33, 3px 3px 0 var(--ink-08)`
                            : "3px 3px 0 var(--ink-08)",
                        }}
                      >
                        {checked && (
                          <span style={{ color: "#fff", fontSize: 28, fontWeight: 800 }}>✓</span>
                        )}
                      </button>
                    );
                  })}
                </Fragment>
              ))}
            </div>
          )}
        </div>

        {/* Footer summary bar */}
        {grid && (
          <div
            className="shrink-0 flex items-center justify-between px-6 py-4"
            style={{ borderTop: "2px solid var(--ink)", background: "var(--surface-alt)" }}
          >
            <span style={{ fontSize: 16, fontWeight: 700 }}>
              {tickCount} / {totalDays} ticked this week
            </span>
            <span
              style={{
                fontFamily: "var(--font-display), sans-serif",
                fontWeight: 800,
                fontSize: 28,
                color: config.color,
              }}
            >
              {formatPence(earnedPence)} earned
            </span>
          </div>
        )}
      </div>
    </Takeover>
  );
}
