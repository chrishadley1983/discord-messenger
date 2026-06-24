"use client";

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
      <div className="bg-surface border border-border rounded-2xl p-4 flex items-center justify-center">
        <span className="text-text-dim text-sm">Sync unavailable</span>
      </div>
    );
  }

  const entries = Object.entries(sync);

  return (
    <div className="bg-surface border border-border rounded-2xl p-4 flex flex-col min-h-0">
      <h3 className="text-sm font-semibold text-text-main flex items-center gap-1.5 mb-3">
        <span>{"\u{1F504}"}</span> Platform Sync
      </h3>

      {entries.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-text-dim text-sm">
          No sync data
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-1.5">
          {entries.map(([type, entry]) => {
            const s = entry.status?.toUpperCase();
            const isOk = s === "COMPLETED" || s === "SUCCESS";
            const isStale = entry.completedAt
              ? Date.now() - new Date(entry.completedAt).getTime() > 24 * 60 * 60 * 1000
              : true;

            return (
              <div key={type} className="flex items-center justify-between px-1 py-1">
                <div className="flex items-center gap-1.5">
                  <span
                    className="w-2 h-2 rounded-full inline-block"
                    style={{
                      background: isOk && !isStale ? "#16A34A" : isOk && isStale ? "#CA8A04" : "#DC2626",
                    }}
                  />
                  <span className="text-xs text-text-mid">{type}</span>
                </div>
                <span className="text-xs text-text-dim">{timeAgo(entry.completedAt)}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
