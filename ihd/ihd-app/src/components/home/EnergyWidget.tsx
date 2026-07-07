"use client";

import { useState, useEffect, useCallback } from "react";
import { Card } from "../ui/Card";
import Icon from "../ui/Icon";
import EnergyDetail from "./EnergyDetail";

interface EnergyData {
  status: string;
  dateLabel: string | null;
  estimated?: boolean;
  electricity: { kwh: number; cost_pounds: number };
  gas: { kwh: number; cost_pounds: number; dateLabel?: string | null };
  isEvDay: boolean;
}

interface LiveData {
  status: string;
  demand_w: number | null;
  today_kwh: number;
  today_cost_pounds: number;
  offpeak_now: boolean;
  stale: boolean;
}

function demandColor(w: number): string {
  if (w < 600) return "var(--good)";
  if (w < 2000) return "var(--warn)";
  return "var(--bad)";
}

export default function EnergyWidget() {
  const [data, setData] = useState<EnergyData | null>(null);
  const [live, setLive] = useState<LiveData | null>(null);
  const [showDetail, setShowDetail] = useState(false);

  const fetchEnergy = useCallback(async () => {
    try {
      const res = await fetch("/api/energy");
      if (res.ok) setData(await res.json());
    } catch {
      // keep last known data
    }
  }, []);

  const fetchLive = useCallback(async () => {
    try {
      const res = await fetch("/api/energy/live");
      if (res.ok) setLive(await res.json());
    } catch {
      // keep last known data
    }
  }, []);

  useEffect(() => {
    fetchEnergy();
    fetchLive();
    const t = setInterval(fetchEnergy, 30 * 60_000);
    const tl = setInterval(fetchLive, 20_000);
    return () => {
      clearInterval(t);
      clearInterval(tl);
    };
  }, [fetchEnergy, fetchLive]);

  const offline = !data || data.status === "offline";
  const noData = data?.status === "no_data";
  const liveOk = live && live.status === "ok" && !live.stale && live.demand_w !== null;

  return (
    <>
    <Card
      section="control"
      chip="Energy"
      chipIcon={<Icon name="zap" size={16} />}
      onClick={() => setShowDetail(true)}
      headerRight={
        data?.dateLabel ? (
          <span className="text-[13px] font-semibold text-ink/50">
            {data.dateLabel}
            {data.estimated ? " (est.)" : ""} ▸
          </span>
        ) : undefined
      }
    >
      {/* Live demand from the Octopus Home Mini (updates every 20s) */}
      {liveOk && (
        <div className="flex items-center gap-2.5 p-2 rounded-xl mb-1.5" style={{ background: "var(--control-tint)" }}>
          <span
            className="inline-block w-2.5 h-2.5 rounded-full animate-pulse flex-shrink-0"
            style={{ background: demandColor(live!.demand_w!) }}
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-baseline gap-1.5">
              <span
                className="font-bold leading-none"
                style={{
                  fontFamily: "var(--font-display), sans-serif",
                  fontSize: 28,
                  color: demandColor(live!.demand_w!),
                }}
              >
                {live!.demand_w! >= 1000
                  ? `${(live!.demand_w! / 1000).toFixed(1)}kW`
                  : `${Math.round(live!.demand_w!)}W`}
              </span>
              <span className="text-[13px] text-ink/50">now</span>
            </div>
            <div className="text-[13px] text-ink/50">
              today {live!.today_kwh}kWh {"·"} £{live!.today_cost_pounds.toFixed(2)}
              {live!.offpeak_now && (
                <span className="ml-1 font-bold text-good">off-peak</span>
              )}
            </div>
          </div>
        </div>
      )}

      {offline || noData ? (
        !liveOk && (
          <div className="text-sm text-ink/50 text-center py-2">
            {noData ? "No data" : "Offline"}
          </div>
        )
      ) : (
        // Side-by-side mini-tiles: the home grid gives this card half a
        // column (shared with Sensors) and clips overflow, so stacked
        // full-width rows never fit below the live-demand tile.
        <div className="grid grid-cols-2 gap-1.5">
          {[
            {
              emoji: "⚡",
              label: "Elec",
              sub: null as string | null,
              kwh: data!.electricity.kwh,
              cost: data!.electricity.cost_pounds,
              color: "var(--warn)",
            },
            {
              emoji: "🔥",
              label: "Gas",
              // Gas has no Home Mini telemetry so it can lag electricity —
              // show its own date when it trails the headline date.
              sub: data!.gas.dateLabel ?? null,
              kwh: data!.gas.kwh,
              cost: data!.gas.cost_pounds,
              color: "var(--calendar)",
            },
          ].map((f) => (
            <div
              key={f.label}
              className="p-2 rounded-xl min-w-0"
              style={{ background: "var(--surface-alt)" }}
            >
              <div className="flex items-center gap-1.5">
                <span className="text-base">{f.emoji}</span>
                <span
                  className="font-bold leading-tight"
                  style={{ fontFamily: "var(--font-display), sans-serif", fontSize: 18, color: f.color }}
                >
                  {f.kwh}
                  <span className="text-[12px] text-ink/50 ml-0.5">kWh</span>
                </span>
              </div>
              <div className="flex items-baseline gap-1.5">
                <span className="text-[13px] font-bold text-ink">£{f.cost.toFixed(2)}</span>
                {f.sub && (
                  <span className="text-[11px] text-ink/50 truncate">{f.sub}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {!offline && !noData && data!.isEvDay && (
        <div className="mt-1.5 text-[13px] font-bold text-warn">
          🔌 EV charge day
        </div>
      )}
    </Card>
    {showDetail && <EnergyDetail onClose={() => setShowDetail(false)} />}
    </>
  );
}
