"use client";

import { useState, useEffect, useCallback } from "react";
import OrdersCard from "./OrdersCard";
import TargetsCard from "./TargetsCard";
import SyncCard from "./SyncCard";
import PnlCard from "./PnlCard";
import QuickActions from "./QuickActions";

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

interface SyncEntry {
  status: string;
  completedAt: string | null;
  error: string | null;
}

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

export interface HBData {
  orders: OrdersData | null;
  metrics: MetricsData | null;
  sync: Record<string, SyncEntry> | null;
  pnl: PnlData | null;
}

export default function HBView() {
  const [data, setData] = useState<HBData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch("/api/hb");
      if (res.ok) setData(await res.json());
    } catch {
      /* keep last known */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const t = setInterval(fetchData, 5 * 60 * 1000);
    return () => clearInterval(t);
  }, [fetchData]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-text-dim text-lg">Loading HB data...</div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col min-h-0 p-3" style={{ animation: "fadeIn .2s ease both" }}>
      {/* Top row: Orders | Targets | Sync (~55%) */}
      <div className="flex-[55] min-h-0 grid grid-cols-3 gap-3 mb-3">
        <OrdersCard orders={data?.orders ?? null} />
        <TargetsCard metrics={data?.metrics ?? null} />
        <SyncCard sync={data?.sync ?? null} />
      </div>

      {/* Bottom row: P&L | Quick Actions (~45%) */}
      <div className="flex-[45] min-h-0 grid grid-cols-[60fr_40fr] gap-3">
        <PnlCard pnl={data?.pnl ?? null} />
        <QuickActions />
      </div>
    </div>
  );
}
