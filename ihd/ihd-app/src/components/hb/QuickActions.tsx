"use client";

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
    <div className="bg-surface border border-border rounded-2xl p-4 flex flex-col min-h-0">
      <h3 className="text-sm font-semibold text-text-main flex items-center gap-1.5 mb-3">
        <span>{"\u{26A1}"}</span> Quick Actions
      </h3>

      <div className="flex-1 grid grid-cols-3 gap-2 content-start">
        {ACTIONS.map((a) => (
          <a
            key={a.path}
            href={`${HB_URL}${a.path}`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col items-center justify-center gap-1 rounded-xl py-3 px-2 no-underline transition-all active:scale-[0.96]"
            style={{ background: "rgba(196,127,10,0.06)", border: "1px solid rgba(196,127,10,0.12)", minHeight: "56px" }}
          >
            <span className="text-xl">{a.icon}</span>
            <span className="text-xs font-medium text-text-mid">{a.label}</span>
          </a>
        ))}
      </div>
    </div>
  );
}
