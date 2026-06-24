"use client";

import { useState, useEffect, useCallback, useRef } from "react";

const CATEGORIES = [
  { key: "room_tidy", label: "Room Tidy", emoji: "\u{1F6CF}\uFE0F" },
  { key: "behaviour", label: "Behaviour", emoji: "\u2B50" },
  { key: "homework", label: "Homework", emoji: "\u{1F4DA}" },
  { key: "special_boost", label: "Boost", emoji: "\u{1F680}" },
] as const;

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
const DAY_LABELS = ["M", "T", "W", "T", "F", "S", "S"];

type Grid = Record<string, Record<string, boolean>>;

interface PocketMoneyGridProps {
  child: "emmie" | "max";
  onClose: () => void;
}

const CHILD_CONFIG = {
  emmie: { name: "Emmie", color: "#8B5CF6" },
  max: { name: "Max", color: "#3B82F6" },
};

export default function PocketMoneyGrid({ child, onClose }: PocketMoneyGridProps) {
  const [grid, setGrid] = useState<Grid | null>(null);
  const [week, setWeek] = useState("");
  const overlayRef = useRef<HTMLDivElement>(null);

  // Which day index is today (0=Mon, 6=Sun)
  const todayIdx = (() => { const d = new Date().getDay(); return d === 0 ? 6 : d - 1; })();

  const fetchGrid = useCallback(async () => {
    try {
      const res = await fetch("/api/kids/pocket-money/grid");
      if (res.ok) {
        const data = await res.json();
        setGrid(data[child]);
        setWeek(data.week);
      }
    } catch { /* ignore */ }
  }, [child]);

  useEffect(() => { fetchGrid(); }, [fetchGrid]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, [onClose]);

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

  // Count ticks for summary
  const tickCount = grid
    ? CATEGORIES.reduce((sum, cat) => sum + DAYS.filter((d) => grid[cat.key]?.[d]).length, 0)
    : 0;
  const totalDays = CATEGORIES.length * 7;

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(26,23,16,0.5)" }}
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div
        className="bg-white rounded-3xl shadow-2xl w-[520px] max-w-[95vw] p-5"
        style={{ animation: "fadeIn 0.2s ease" }}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold" style={{ color: config.color }}>
            {config.name}&apos;s Weekly Grid
          </h2>
          <button
            onClick={onClose}
            className="text-2xl text-text-dim cursor-pointer p-1"
            style={{ minWidth: "44px", minHeight: "44px" }}
          >
            &times;
          </button>
        </div>

        {!grid ? (
          <div className="text-center text-text-dim py-8">Loading...</div>
        ) : (
          <>
            {/* Grid */}
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    <th className="text-left text-xs text-text-dim pb-2 pr-2 w-24" />
                    {DAY_LABELS.map((label, i) => (
                      <th
                        key={i}
                        className="text-center text-xs font-bold pb-2 px-0.5"
                        style={{
                          color: i === todayIdx ? config.color : "#7a7060",
                          width: "13%",
                        }}
                      >
                        {label}
                        {i === todayIdx && (
                          <div
                            className="mx-auto mt-0.5 rounded-full"
                            style={{ width: 4, height: 4, background: config.color }}
                          />
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {CATEGORIES.map((cat) => (
                    <tr key={cat.key}>
                      <td className="text-xs font-medium text-text-mid pr-2 py-1.5 whitespace-nowrap">
                        <span className="mr-1">{cat.emoji}</span>
                        {cat.label}
                      </td>
                      {DAYS.map((day, i) => {
                        const checked = grid[cat.key]?.[day] ?? false;
                        const isFuture = i > todayIdx;
                        return (
                          <td key={day} className="text-center py-1.5 px-0.5">
                            <button
                              onClick={() => toggle(cat.key, day, checked)}
                              className="w-10 h-10 rounded-xl flex items-center justify-center cursor-pointer transition-all active:scale-90"
                              style={{
                                background: checked
                                  ? `${config.color}18`
                                  : isFuture
                                    ? "#f8f7f4"
                                    : "#fef2f2",
                                border: `2px solid ${
                                  checked
                                    ? config.color
                                    : isFuture
                                      ? "#e5e2d9"
                                      : "#fecaca"
                                }`,
                              }}
                            >
                              {checked ? (
                                <span className="text-lg font-bold" style={{ color: config.color }}>
                                  {"\u2713"}
                                </span>
                              ) : isFuture ? (
                                <span className="text-text-dim text-xs">{"\u2022"}</span>
                              ) : (
                                <span className="text-red-300 text-lg">{"\u2717"}</span>
                              )}
                            </button>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Summary bar */}
            <div className="mt-4 pt-3 border-t border-border flex items-center justify-between">
              <span className="text-xs text-text-mid">
                {tickCount} / {totalDays} this week
              </span>
              <div className="h-2 flex-1 mx-3 rounded-full bg-surface-alt overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${(tickCount / totalDays) * 100}%`,
                    background: config.color,
                  }}
                />
              </div>
              <span className="text-xs font-bold" style={{ color: config.color }}>
                {tickCount >= totalDays * 0.8 ? "\u{1F31F}" : tickCount >= totalDays * 0.5 ? "\u{1F44D}" : "\u{1F4AA}"}
              </span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
