"use client";

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
  return `\u00A3${Math.abs(v).toFixed(0)}`;
}

function monthLabel(m: string): string {
  const [y, mo] = m.split("-");
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${names[parseInt(mo) - 1]} ${y}`;
}

function PnlColumn({ data, label }: { data: PnlMonth; label: string }) {
  const profitColor = data.profit >= 0 ? "#16A34A" : "#DC2626";

  return (
    <div className="flex-1">
      <div className="text-xs font-semibold text-text-mid mb-2 text-center">{label}</div>

      <div className="space-y-1.5 text-xs">
        <div className="flex justify-between">
          <span className="text-text-mid">Revenue</span>
          <span className="font-semibold text-text-main">{fmt(data.revenue)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-text-mid">Fees</span>
          <span className="text-red-500">-{fmt(data.fees)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-text-mid">Stock</span>
          <span className="text-red-500">-{fmt(data.cogs)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-text-mid">Other</span>
          <span className="text-red-500">-{fmt(data.other)}</span>
        </div>

        <div className="border-t border-border pt-1.5 flex justify-between">
          <span className="font-semibold text-text-main">Profit</span>
          <span className="font-bold font-serif text-base" style={{ color: profitColor }}>
            {data.profit < 0 ? "-" : ""}{fmt(data.profit)}
          </span>
        </div>
      </div>
    </div>
  );
}

export default function PnlCard({ pnl }: { pnl: PnlData | null }) {
  if (!pnl) {
    return (
      <div className="bg-surface border border-border rounded-2xl p-4 flex items-center justify-center">
        <span className="text-text-dim text-sm">P&L unavailable</span>
      </div>
    );
  }

  return (
    <div className="bg-surface border border-border rounded-2xl p-4 flex flex-col min-h-0">
      <h3 className="text-sm font-semibold text-text-main flex items-center gap-1.5 mb-3">
        <span>{"\u{1F4B0}"}</span> Profit & Loss
      </h3>

      <div className="flex-1 flex gap-4 min-h-0">
        <PnlColumn data={pnl.lastMonth} label={monthLabel(pnl.lastMonth.month)} />
        <div className="w-px bg-border" />
        <PnlColumn data={pnl.thisMonth} label={monthLabel(pnl.thisMonth.month)} />
      </div>
    </div>
  );
}
