"use client";

import { Card } from "@/components/ui/Card";
import Icon from "@/components/ui/Icon";

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
  const color = pct >= 100 ? "var(--good)" : pct >= 60 ? "var(--warn)" : "var(--bad)";

  return (
    <div className="mb-3">
      <div className="flex justify-between items-baseline mb-1 gap-2">
        <span className="text-sm shrink-0" style={{ color: "var(--ink-60)" }}>
          {label}
        </span>
        <span
          className="tabular-nums font-bold text-sm text-right"
          style={{ fontFamily: "var(--font-display)", color }}
        >
          {"£"}
          {current.toLocaleString("en-GB", { maximumFractionDigits: 0 })} / {"£"}
          {target.toLocaleString("en-GB", { maximumFractionDigits: 0 })}
        </span>
      </div>
      <div
        className="rounded-full overflow-hidden"
        style={{ height: "14px", background: "var(--ink-08)" }}
      >
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
      <Card section="hb" chip="Targets" chipIcon={<Icon name="target" size={16} />} className="min-h-0">
        <div className="flex-1 flex items-center justify-center">
          <span className="text-sm" style={{ color: "var(--ink-60)" }}>
            Targets unavailable
          </span>
        </div>
      </Card>
    );
  }

  const { ebayValue, amazonValue, blValue, listedValue, soldValue, targets } = metrics;
  const dayOfWeek = new Date().getDay();
  const daysSoFar = dayOfWeek === 0 ? 7 : dayOfWeek;
  const weeklyListedTarget = targets.dailyListedValue * 7;
  const weeklySoldTarget = targets.dailySoldValue * 7;

  return (
    <Card
      section="hb"
      chip="This Week"
      chipIcon={<Icon name="target" size={16} />}
      className="min-h-0"
      headerRight={
        <span className="text-sm font-semibold" style={{ color: "var(--ink-60)" }}>
          Day {daysSoFar}/7
        </span>
      }
    >
      <div className="flex-1 overflow-y-auto min-h-0">
        <ProgressRow label="eBay Listed" current={ebayValue} target={targets.ebayValue} />
        <ProgressRow label="Amazon Listed" current={amazonValue} target={targets.amazonValue} />
        <ProgressRow label="BrickLink" current={blValue} target={targets.blWeeklyValue} />
        <ProgressRow label="Week Listed" current={listedValue} target={weeklyListedTarget} />
        <ProgressRow label="Week Sold" current={soldValue} target={weeklySoldTarget} />
      </div>
    </Card>
  );
}
