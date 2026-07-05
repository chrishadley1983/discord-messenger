"use client";

import { Card } from "@/components/ui/Card";
import Icon from "@/components/ui/Icon";
import EmptyState from "@/components/ui/EmptyState";

interface PnlMonth {
  month: string;
  revenue: number;
  fees: number;
  cogs: number;
  other: number;
  profit: number;
}

interface PnlData {
  thisMonth: PnlMonth;
  lastMonth: PnlMonth;
}

function fmt(v: number): string {
  return `£${Math.abs(v).toFixed(0)}`;
}

function monthLabel(m: string): string {
  const [y, mo] = m.split("-");
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${names[parseInt(mo) - 1]} ${y}`;
}

function PnlColumn({ data, label }: { data: PnlMonth; label: string }) {
  const profitColor = data.profit >= 0 ? "var(--good)" : "var(--bad)";

  return (
    <div className="flex-1">
      <div className="text-sm font-semibold mb-2 text-center" style={{ color: "var(--ink-60)" }}>
        {label}
      </div>

      <div className="flex flex-col gap-1.5 text-sm">
        <div className="flex justify-between">
          <span style={{ color: "var(--ink-60)" }}>Revenue</span>
          <span className="font-semibold tabular-nums" style={{ color: "var(--ink)" }}>
            {fmt(data.revenue)}
          </span>
        </div>
        <div className="flex justify-between">
          <span style={{ color: "var(--ink-60)" }}>Fees</span>
          <span className="tabular-nums" style={{ color: "var(--bad)" }}>
            -{fmt(data.fees)}
          </span>
        </div>
        <div className="flex justify-between">
          <span style={{ color: "var(--ink-60)" }}>Stock</span>
          <span className="tabular-nums" style={{ color: "var(--bad)" }}>
            -{fmt(data.cogs)}
          </span>
        </div>
        <div className="flex justify-between">
          <span style={{ color: "var(--ink-60)" }}>Other</span>
          <span className="tabular-nums" style={{ color: "var(--bad)" }}>
            -{fmt(data.other)}
          </span>
        </div>

        <div className="pt-1.5 flex justify-between items-center" style={{ borderTop: "2px solid var(--ink-12)" }}>
          <span className="font-semibold" style={{ color: "var(--ink)" }}>
            Profit
          </span>
          <span
            className="tabular-nums"
            style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "18px", color: profitColor }}
          >
            {data.profit < 0 ? "-" : ""}
            {fmt(data.profit)}
          </span>
        </div>
      </div>
    </div>
  );
}

/** Decorative LEGO stud strip — CSS circles only, purely visual. */
function StudStrip() {
  return (
    <div
      aria-hidden="true"
      className="flex items-center justify-center gap-2.5 pt-3 mt-2 shrink-0"
      style={{ borderTop: "1px dashed var(--ink-12)" }}
    >
      {Array.from({ length: 8 }).map((_, i) => (
        <span
          key={i}
          className="inline-block rounded-full shrink-0"
          style={{ width: "12px", height: "12px", background: "var(--hb-tint)", border: "2px solid var(--hb)" }}
        />
      ))}
    </div>
  );
}

export default function PnlCard({ pnl }: { pnl: PnlData | null }) {
  if (!pnl) {
    return (
      <Card section="hb" chip="Profit & Loss" chipIcon={<Icon name="coins" size={16} />} className="min-h-0">
        <EmptyState icon="coins" headline="P&L unavailable" compact />
      </Card>
    );
  }

  return (
    <Card section="hb" chip="Profit & Loss" chipIcon={<Icon name="coins" size={16} />} className="min-h-0">
      <div className="flex-1 flex gap-4 min-h-0">
        <PnlColumn data={pnl.lastMonth} label={monthLabel(pnl.lastMonth.month)} />
        <div className="w-px" style={{ background: "var(--ink-12)" }} />
        <PnlColumn data={pnl.thisMonth} label={monthLabel(pnl.thisMonth.month)} />
      </div>
      <StudStrip />
    </Card>
  );
}
