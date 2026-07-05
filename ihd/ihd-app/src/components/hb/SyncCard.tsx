"use client";

import { Card } from "@/components/ui/Card";

interface SyncEntry {
  status: string;
  completedAt: string | null;
  error: string | null;
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "never";
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function SyncCard({ sync }: { sync: Record<string, SyncEntry> | null }) {
  if (!sync) {
    return (
      <Card section="hb" chip="Sync" chipIcon={"\u{1F504}"} className="min-h-0">
        <div className="flex-1 flex items-center justify-center">
          <span className="text-sm" style={{ color: "var(--ink-60)" }}>
            Sync unavailable
          </span>
        </div>
      </Card>
    );
  }

  const entries = Object.entries(sync);

  return (
    <Card section="hb" chip="Sync" chipIcon={"\u{1F504}"} className="min-h-0">
      {entries.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-sm" style={{ color: "var(--ink-60)" }}>
          No sync data
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto flex flex-col gap-2 min-h-0">
          {entries.map(([type, entry]) => {
            const s = entry.status?.toUpperCase();
            const isOk = s === "COMPLETED" || s === "SUCCESS";
            const isStale = entry.completedAt
              ? Date.now() - new Date(entry.completedAt).getTime() > 24 * 60 * 60 * 1000
              : true;
            const dotColor = isOk && !isStale ? "var(--good)" : isOk && isStale ? "var(--warn)" : "var(--bad)";

            return (
              <div key={type} className="flex items-center justify-between px-1 py-1">
                <div className="flex items-center gap-2.5">
                  <span
                    className="inline-block rounded-full shrink-0"
                    style={{ width: "16px", height: "16px", background: dotColor, border: "2px solid var(--ink)" }}
                  />
                  <span className="text-sm" style={{ color: "var(--ink)" }}>
                    {type}
                  </span>
                </div>
                <span className="text-sm" style={{ color: "var(--ink-60)" }}>
                  {timeAgo(entry.completedAt)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
