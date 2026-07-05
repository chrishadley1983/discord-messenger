"use client";

import type { ReactNode } from "react";
import { Card } from "@/components/ui/Card";

interface OrdersPlatform {
  count: number;
  overdue: number;
  urgent: number;
}

interface OrdersData {
  platforms: Record<string, OrdersPlatform>;
  totalOrders: number;
  totalOverdue: number;
  totalUrgent: number;
}

function StickerBadge({
  children,
  tone,
  rotate,
}: {
  children: ReactNode;
  tone: "bad" | "warn";
  rotate: number;
}) {
  const bg = tone === "bad" ? "var(--bad)" : "var(--warn)";
  const color = tone === "bad" ? "#fff" : "var(--ink)";
  return (
    <span
      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full font-bold text-sm shrink-0"
      style={{
        background: bg,
        color,
        border: "2px solid var(--ink)",
        transform: `rotate(${rotate}deg)`,
      }}
    >
      {children}
    </span>
  );
}

export default function OrdersCard({ orders }: { orders: OrdersData | null }) {
  if (!orders) {
    return (
      <Card section="hb" chip="Dispatch" chipIcon={"\u{1F4E6}"} className="min-h-0">
        <div className="flex-1 flex items-center justify-center">
          <span className="text-sm" style={{ color: "var(--ink-60)" }}>
            Orders unavailable
          </span>
        </div>
      </Card>
    );
  }

  const { platforms, totalOrders, totalOverdue, totalUrgent } = orders;
  const hasIssues = totalOverdue > 0 || totalUrgent > 0;

  return (
    <Card
      section="hb"
      chip="Dispatch"
      chipIcon={"\u{1F4E6}"}
      className="min-h-0"
      headerRight={
        <span
          className="tabular-nums"
          style={{
            fontFamily: "var(--font-display)",
            fontWeight: 800,
            fontSize: "44px",
            lineHeight: 1,
            color: hasIssues ? "var(--bad)" : "var(--good)",
          }}
        >
          {totalOrders}
        </span>
      }
    >
      {totalOrders === 0 ? (
        <div className="flex-1 flex items-center justify-center text-sm text-center" style={{ color: "var(--ink-60)" }}>
          All clear — no orders pending
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto flex flex-col gap-2 min-h-0">
          {(totalOverdue > 0 || totalUrgent > 0) && (
            <div className="flex flex-wrap gap-2 mb-1">
              {totalOverdue > 0 && (
                <StickerBadge tone="bad" rotate={-1.5}>
                  {"\u{1F6A8}"} {totalOverdue} OVERDUE
                </StickerBadge>
              )}
              {totalUrgent > 0 && (
                <StickerBadge tone="warn" rotate={1.5}>
                  {"⚠"} {totalUrgent} due &lt;2h
                </StickerBadge>
              )}
            </div>
          )}

          {Object.entries(platforms).map(([platform, data]) => (
            <div key={platform} className="flex items-center justify-between px-1">
              <span className="text-sm" style={{ color: "var(--ink-60)" }}>
                {platform}
              </span>
              <div className="flex items-center gap-2">
                <span
                  className="text-sm font-semibold tabular-nums"
                  style={{ fontFamily: "var(--font-display)", color: "var(--ink)" }}
                >
                  {data.count}
                </span>
                {data.overdue > 0 && (
                  <span
                    className="text-sm px-2 py-0.5 rounded-full font-semibold"
                    style={{ background: "var(--bad)", color: "#fff", border: "2px solid var(--ink)" }}
                  >
                    {data.overdue} late
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
