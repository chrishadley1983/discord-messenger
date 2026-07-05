"use client";

import { Card } from "@/components/ui/Card";

const HB_URL = "https://hadley-bricks-inventory-management.vercel.app";

const ACTIONS = [
  { label: "Workflow", icon: "\u{1F4CB}", path: "/workflow" },
  { label: "Inventory", icon: "\u{1F4E6}", path: "/inventory" },
  { label: "New Listing", icon: "\u{2795}", path: "/inventory/new" },
  { label: "Orders", icon: "\u{1F6D2}", path: "/orders" },
  { label: "Reports", icon: "\u{1F4CA}", path: "/reports" },
  { label: "Settings", icon: "\u{2699}", path: "/settings" },
];

export default function QuickActions() {
  return (
    <Card section="hb" chip="Quick Actions" chipIcon={"⚡"} className="min-h-0">
      <div className="flex-1 grid grid-cols-3 gap-2.5 content-start min-h-0">
        {ACTIONS.map((a) => (
          <a
            key={a.path}
            href={`${HB_URL}${a.path}`}
            target="_blank"
            rel="noopener noreferrer"
            className="pressable flex flex-col items-center justify-center gap-1 no-underline"
            style={{
              minHeight: "64px",
              background: "var(--hb-tint)",
              border: "2px solid var(--ink)",
              borderRadius: "16px",
              boxShadow: "3px 3px 0 var(--ink-08)",
            }}
          >
            <span className="text-2xl">{a.icon}</span>
            <span className="text-sm font-semibold text-center" style={{ color: "var(--ink)" }}>
              {a.label}
            </span>
          </a>
        ))}
      </div>
    </Card>
  );
}
