"use client";

/**
 * Countdowns — replaced the Japan Trip widget (trip reached 0 days, Jul 2026).
 * Hero = the next upcoming event (big day count); two more below.
 * Tap → Modal with the full list. Data: /api/countdowns (.data/countdowns.json).
 */

import { useState, useEffect, useCallback } from "react";
import { Card } from "../ui/Card";
import Modal from "../ui/Modal";
import Icon from "../ui/Icon";

interface Countdown {
  id: string;
  label: string;
  emoji: string;
  date: string;
  dateLabel: string;
  days: number;
}

function daysLabel(days: number): string {
  if (days === 0) return "TODAY!";
  if (days === 1) return "tomorrow";
  return `${days} days`;
}

export default function CountdownWidget() {
  const [items, setItems] = useState<Countdown[]>([]);
  const [showAll, setShowAll] = useState(false);

  const fetchItems = useCallback(async () => {
    try {
      const res = await fetch("/api/countdowns");
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.countdowns)) setItems(data.countdowns);
      }
    } catch {
      // keep last known
    }
  }, []);

  useEffect(() => {
    fetchItems();
    const t = setInterval(fetchItems, 60 * 60 * 1000); // hourly
    return () => clearInterval(t);
  }, [fetchItems]);

  const [next, ...rest] = items;

  return (
    <>
      <Card
        chip="Countdowns"
        chipIcon={<Icon name="flag" size={16} />}
        section="home"
        onClick={() => setShowAll(true)}
        className="flex-1 min-h-0"
      >
        {!next ? (
          <div
            className="flex-1 flex items-center justify-center text-center"
            style={{ color: "var(--ink-30)", fontSize: 15 }}
          >
            Nothing coming up
          </div>
        ) : (
          <div className="flex-1 min-h-0 flex flex-col">
            {/* Hero: next event */}
            <div className="flex items-center gap-3">
              <span
                className="leading-none"
                style={{
                  fontSize: 40,
                  display: "inline-block",
                  transform: "rotate(-2deg)",
                }}
              >
                {next.emoji}
              </span>
              <div className="min-w-0 flex-1">
                <div
                  className="truncate"
                  style={{
                    fontFamily: "var(--font-display), sans-serif",
                    fontWeight: 700,
                    fontSize: 18,
                  }}
                >
                  {next.label}
                </div>
                <div className="text-sm" style={{ color: "var(--text-mid)" }}>
                  {next.dateLabel}
                </div>
              </div>
              <div className="text-right shrink-0 flex items-baseline gap-1.5">
                <span
                  className="leading-none"
                  style={{
                    fontFamily: "var(--font-display), sans-serif",
                    fontWeight: 800,
                    fontSize: next.days === 0 ? 24 : 34,
                    color: next.days <= 7 ? "var(--meals)" : "var(--ink)",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {next.days === 0 ? "TODAY!" : next.days}
                </span>
                {next.days > 0 && (
                  <span className="text-xs" style={{ color: "var(--text-mid)" }}>
                    {next.days === 1 ? "day" : "days"}
                  </span>
                )}
              </div>
            </div>

            {/* Next two, small */}
            {rest.length > 0 && (
              <div
                className="mt-3 pt-2 flex flex-col gap-1.5"
                style={{ borderTop: "2px solid var(--ink-08)" }}
              >
                {rest.slice(0, 2).map((c) => (
                  <div key={c.id} className="flex items-center gap-2 text-sm">
                    <span className="text-base leading-none">{c.emoji}</span>
                    <span className="flex-1 truncate font-semibold">{c.label}</span>
                    <span
                      style={{
                        fontFamily: "var(--font-display), sans-serif",
                        fontWeight: 700,
                        color: "var(--text-mid)",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {daysLabel(c.days)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </Card>

      {showAll && (
        <Modal
          onClose={() => setShowAll(false)}
          accent="var(--home)"
          title="Countdowns"
          maxWidth={560}
        >
          <div className="flex flex-col gap-1 p-4">
            {items.map((c) => (
              <div
                key={c.id}
                className="flex items-center gap-3"
                style={{
                  minHeight: 56,
                  padding: "8px 14px",
                  borderRadius: 14,
                  background: c.days <= 7 ? "var(--home-tint)" : "transparent",
                }}
              >
                <span className="text-2xl leading-none">{c.emoji}</span>
                <div className="flex-1 min-w-0">
                  <div className="font-bold truncate" style={{ fontSize: 16 }}>
                    {c.label}
                  </div>
                  <div className="text-sm" style={{ color: "var(--text-mid)" }}>
                    {c.dateLabel}
                  </div>
                </div>
                <span
                  style={{
                    fontFamily: "var(--font-display), sans-serif",
                    fontWeight: 800,
                    fontSize: 20,
                    color: c.days <= 7 ? "var(--meals)" : "var(--ink)",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {daysLabel(c.days)}
                </span>
              </div>
            ))}
            <div className="text-xs mt-2 px-2" style={{ color: "var(--ink-30)" }}>
              Edit on the Pi: ~/ihd-app/.data/countdowns.json
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
