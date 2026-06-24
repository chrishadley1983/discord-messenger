"use client";

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

export default function OrdersCard({ orders }: { orders: OrdersData | null }) {
  if (!orders) {
    return (
      <div className="bg-surface border border-border rounded-2xl p-4 flex items-center justify-center">
        <span className="text-text-dim text-sm">Orders unavailable</span>
      </div>
    );
  }

  const { platforms, totalOrders, totalOverdue, totalUrgent } = orders;
  const hasIssues = totalOverdue > 0 || totalUrgent > 0;

  return (
    <div className="bg-surface border border-border rounded-2xl p-4 flex flex-col min-h-0">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-text-main flex items-center gap-1.5">
          <span>{"\u{1F4E6}"}</span> Orders to Dispatch
        </h3>
        <span
          className="text-2xl font-bold font-serif"
          style={{ color: hasIssues ? "#DC2626" : "#16A34A" }}
        >
          {totalOrders}
        </span>
      </div>

      {totalOrders === 0 ? (
        <div className="flex-1 flex items-center justify-center text-text-dim text-sm">
          All clear — no orders pending
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-2">
          {totalOverdue > 0 && (
            <div className="rounded-xl px-3 py-2" style={{ background: "rgba(220,38,38,0.08)" }}>
              <span className="text-xs font-semibold" style={{ color: "#DC2626" }}>
                {"\u{1F6A8}"} {totalOverdue} OVERDUE
              </span>
            </div>
          )}
          {totalUrgent > 0 && (
            <div className="rounded-xl px-3 py-2" style={{ background: "rgba(234,179,8,0.08)" }}>
              <span className="text-xs font-semibold" style={{ color: "#CA8A04" }}>
                {"\u{26A0}"} {totalUrgent} due within 2h
              </span>
            </div>
          )}

          {Object.entries(platforms).map(([platform, data]) => (
            <div key={platform} className="flex items-center justify-between px-1">
              <span className="text-sm text-text-mid">{platform}</span>
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-text-main">{data.count}</span>
                {data.overdue > 0 && (
                  <span className="text-xs px-1.5 py-0.5 rounded-full" style={{ background: "rgba(220,38,38,0.1)", color: "#DC2626" }}>
                    {data.overdue} late
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
