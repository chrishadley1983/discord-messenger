"use client";

import { Card } from "@/components/ui/Card";
import Icon, { type IconName } from "@/components/ui/Icon";

const HB_URL = "https://hadley-bricks-inventory-management.vercel.app";

const ACTIONS: { label: string; icon: IconName; path: string }[] = [
  { label: "Workflow", icon: "clipboard", path: "/workflow" },
  { label: "Inventory", icon: "package", path: "/inventory" },
  { label: "New Listing", icon: "plus", path: "/inventory/new" },
  { label: "Orders", icon: "cart", path: "/orders" },
  { label: "Reports", icon: "chart", path: "/reports" },
  { label: "Settings", icon: "gear", path: "/settings" },
];

export default function QuickActions() {
  return (
    <Card section="hb" chip="Quick Actions" chipIcon={<Icon name="zap" size={16} />} className="min-h-0">
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
            <Icon name={a.icon} size={22} style={{ color: "var(--hb)" }} />
            <span className="text-sm font-semibold text-center" style={{ color: "var(--ink)" }}>
              {a.label}
            </span>
          </a>
        ))}
      </div>
    </Card>
  );
}
