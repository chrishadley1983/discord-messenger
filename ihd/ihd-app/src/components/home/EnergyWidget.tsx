"use client";

import { useState, useEffect, useCallback } from "react";

interface EnergyData {
  status: string;
  dateLabel: string | null;
  electricity: { kwh: number; cost_pounds: number };
  gas: { kwh: number; cost_pounds: number };
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
  if (w < 600) return "var(--green, #4ade80)";
  if (w < 2000) return "var(--accent)";
  return "var(--red, #f87171)";
}

export default function EnergyWidget() {
  const [data, setData] = useState<EnergyData | null>(null);
  const [live, setLive] = useState<LiveData | null>(null);

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

  const title = data?.dateLabel
    ? `Energy — ${data.dateLabel}`
    : "Energy";

  return (
    <div className="bg-surface border border-border rounded-2xl p-3 shadow-sm flex flex-col">
      <div className="text-xs font-bold uppercase tracking-widest text-text-mid mb-2">
        {title}
      </div>

      {/* Live demand from the Octopus Home Mini (updates every 20s) */}
      {liveOk && (
        <div className="flex items-center gap-2 p-2 bg-surface-alt rounded-xl mb-1.5">
          <span
            className="inline-block w-2 h-2 rounded-full animate-pulse"
            style={{ background: demandColor(live!.demand_w!) }}
          />
          <div className="flex-1 min-w-0">
            <div
              className="font-serif text-2xl font-extralight leading-tight"
              style={{ color: demandColor(live!.demand_w!) }}
            >
              {live!.demand_w! >= 1000
                ? `${(live!.demand_w! / 1000).toFixed(1)}kW`
                : `${Math.round(live!.demand_w!)}W`}
              <span className="text-[0.6rem] text-text-dim ml-1">now</span>
            </div>
            <div className="text-[0.65rem] text-text-dim">
              today {live!.today_kwh}kWh {"·"} {"£"}
              {live!.today_cost_pounds.toFixed(2)}
              {live!.offpeak_now && (
                <span className="ml-1 font-bold" style={{ color: "var(--green, #4ade80)" }}>
                  off-peak
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {offline || noData ? (
        !liveOk && (
          <div className="text-xs text-text-dim text-center py-2">
            {noData ? "No data" : "Offline"}
          </div>
        )
      ) : (
        <div className="flex flex-col gap-1.5">
          {[
            {
              emoji: "⚡",
              label: "Elec",
              kwh: data!.electricity.kwh,
              cost: data!.electricity.cost_pounds,
              color: "var(--accent)",
            },
            {
              emoji: "🔥",
              label: "Gas",
              kwh: data!.gas.kwh,
              cost: data!.gas.cost_pounds,
              color: "var(--blue)",
            },
          ].map((f) => (
            <div
              key={f.label}
              className="flex items-center gap-2 p-2 bg-surface-alt rounded-xl"
            >
              <span className="text-base">{f.emoji}</span>
              <div className="flex-1 min-w-0">
                <div
                  className="font-serif text-lg font-extralight leading-tight"
                  style={{ color: f.color }}
                >
                  {f.kwh}
                  <span className="text-[0.6rem] text-text-dim ml-0.5">kWh</span>
                </div>
              </div>
              <div className="text-sm font-bold text-text">
                {"£"}{f.cost.toFixed(2)}
              </div>
            </div>
          ))}
        </div>
      )}

      {!offline && !noData && data!.isEvDay && (
        <div className="mt-1.5 text-[0.65rem] font-bold" style={{ color: "var(--accent)" }}>
          {"🔌"} EV charge day
        </div>
      )}
    </div>
  );
}
