"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Card } from "../ui/Card";
import Icon from "../ui/Icon";

interface HbOrders {
  platforms: Record<string, { count: number; overdue: number; urgent: number }>;
  totalOrders: number;
  totalOverdue: number;
  totalUrgent: number;
}

interface HbPnl {
  thisMonth: { month: string; revenue: number };
}

interface HbResponse {
  orders: HbOrders | null;
  metrics: unknown;
  sync: unknown;
  pnl: HbPnl | null;
}

export default function HadleyWidget() {
  const router = useRouter();
  const [data, setData] = useState<HbResponse | null>(null);
  const [failed, setFailed] = useState(false);

  const fetchHb = useCallback(async () => {
    try {
      const res = await fetch("/api/hb");
      if (res.ok) {
        setData(await res.json());
        setFailed(false);
      } else {
        setFailed(true);
      }
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    fetchHb();
    const t = setInterval(fetchHb, 5 * 60 * 1000); // 5 min
    return () => clearInterval(t);
  }, [fetchHb]);

  const orders = data?.orders;
  const revenue = data?.pnl?.thisMonth?.revenue;
  const noData = !data && failed;

  return (
    <Card
      section="hb"
      chip="Hadley Bricks"
      chipIcon={<Icon name="brick" size={16} />}
      onClick={() => router.push("/chris")}
    >
      <div className="grid grid-cols-2 gap-2.5">
        <div className="text-center py-2.5 px-2 rounded-xl" style={{ background: "var(--hb-tint)" }}>
          <div
            className="font-bold"
            style={{
              fontFamily: "var(--font-display), sans-serif",
              fontSize: 30,
              color: !orders ? "var(--hb)" : orders.totalOverdue > 0 ? "var(--bad)" : "var(--good)",
            }}
          >
            {orders ? orders.totalOrders : "—"}
          </div>
          <div className="text-[13px] text-ink/50 mt-0.5 uppercase tracking-wide font-semibold">
            To Dispatch
          </div>
          {orders && orders.totalOverdue > 0 && (
            <div className="text-[13px] font-bold text-bad mt-0.5">
              {orders.totalOverdue} overdue
            </div>
          )}
        </div>
        <div className="text-center py-2.5 px-2 rounded-xl" style={{ background: "var(--hb-tint)" }}>
          <div
            className="font-bold"
            style={{ fontFamily: "var(--font-display), sans-serif", fontSize: 30, color: "var(--hb)" }}
          >
            {revenue != null ? `£${Math.round(revenue).toLocaleString()}` : "—"}
          </div>
          <div className="text-[13px] text-ink/50 mt-0.5 uppercase tracking-wide font-semibold">
            This Month
          </div>
        </div>
      </div>

      {noData && (
        <div className="text-sm text-ink/40 text-center mt-2">Hadley Bricks unreachable</div>
      )}
    </Card>
  );
}
