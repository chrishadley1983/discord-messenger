"use client";

interface MetricsData {
  listedValue: number;
  soldValue: number;
  blValue: number;
  ebayValue: number;
  amazonValue: number;
  targets: {
    ebayValue: number;
    amazonValue: number;
    blWeeklyValue: number;
    dailyListedValue: number;
    dailySoldValue: number;
  };
}

function ProgressRow({ label, current, target }: { label: string; current: number; target: number }) {
  const pct = target > 0 ? Math.min(100, (current / target) * 100) : 0;
  const color = pct >= 100 ? "#16A34A" : pct >= 60 ? "#CA8A04" : "#DC2626";

  return (
    <div className="mb-2.5">
      <div className="flex justify-between text-xs mb-0.5">
        <span className="text-text-mid">{label}</span>
        <span className="font-semibold" style={{ color }}>
          {"\u00A3"}{current.toLocaleString("en-GB", { maximumFractionDigits: 0 })} / {"\u00A3"}{target.toLocaleString("en-GB", { maximumFractionDigits: 0 })}
        </span>
      </div>
      <div className="h-2.5 rounded-full overflow-hidden" style={{ background: "rgba(0,0,0,0.06)" }}>
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  );
}

export default function TargetsCard({ metrics }: { metrics: MetricsData | null }) {
  if (!metrics) {
    return (
      <div className="bg-surface border border-border rounded-2xl p-4 flex items-center justify-center">
        <span className="text-text-dim text-sm">Targets unavailable</span>
      </div>
    );
  }

  const { ebayValue, amazonValue, blValue, listedValue, soldValue, targets } = metrics;
  const dayOfWeek = new Date().getDay();
  const daysSoFar = dayOfWeek === 0 ? 7 : dayOfWeek;
  const weeklyListedTarget = targets.dailyListedValue * 7;
  const weeklySoldTarget = targets.dailySoldValue * 7;

  return (
    <div className="bg-surface border border-border rounded-2xl p-4 flex flex-col min-h-0">
      <h3 className="text-sm font-semibold text-text-main flex items-center gap-1.5 mb-3">
        <span>{"\u{1F3AF}"}</span> This Week (Day {daysSoFar}/7)
      </h3>

      <div className="flex-1 overflow-y-auto">
        <ProgressRow label="eBay Listed" current={ebayValue} target={targets.ebayValue} />
        <ProgressRow label="Amazon Listed" current={amazonValue} target={targets.amazonValue} />
        <ProgressRow label="BrickLink" current={blValue} target={targets.blWeeklyValue} />
        <ProgressRow label="Week Listed" current={listedValue} target={weeklyListedTarget} />
        <ProgressRow label="Week Sold" current={soldValue} target={weeklySoldTarget} />
      </div>
    </div>
  );
}
