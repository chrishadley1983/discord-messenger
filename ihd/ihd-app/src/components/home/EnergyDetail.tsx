"use client";

/**
 * Energy detail takeover — opened from the home Energy card.
 * Live demand + latest-day stat tiles, half-hourly profile, 14-day history.
 * Data: /api/energy/history (Supabase daily summary + half-hourly consumption)
 * and /api/energy/live (demand watts).
 */

import { useState, useEffect, useCallback } from "react";
import Takeover from "../ui/Takeover";

interface DailyPoint {
  date: string;
  dayLabel: string;
  dayNum: number;
  elec_kwh: number;
  elec_cost: number;
  gas_kwh: number;
  gas_cost: number;
  ev: boolean;
  total_cost: number;
}

interface HistoryData {
  status: string;
  daily?: DailyPoint[];
  profile?: { time: string; kwh: number }[];
  profileDateLabel?: string;
}

function StatTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div
      className="flex-1 text-center py-3 px-2"
      style={{ background: "var(--control-tint)", borderRadius: 16 }}
    >
      <div
        style={{
          fontFamily: "var(--font-display), sans-serif",
          fontWeight: 800,
          fontSize: 30,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {value}
      </div>
      <div className="text-xs uppercase font-bold" style={{ color: "var(--text-mid)", letterSpacing: "0.05em" }}>
        {label}
      </div>
      {sub && (
        <div className="text-xs" style={{ color: "var(--text-dim)" }}>
          {sub}
        </div>
      )}
    </div>
  );
}

export default function EnergyDetail({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<HistoryData | null>(null);
  const [liveW, setLiveW] = useState<number | null>(null);

  useEffect(() => {
    fetch("/api/energy/history")
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData({ status: "offline" }));
  }, []);

  const fetchLive = useCallback(async () => {
    try {
      const res = await fetch("/api/energy/live");
      if (res.ok) {
        const d = await res.json();
        if (typeof d.demand_w === "number") setLiveW(d.demand_w);
      }
    } catch {
      /* keep last */
    }
  }, []);

  useEffect(() => {
    fetchLive();
    const t = setInterval(fetchLive, 20000);
    return () => clearInterval(t);
  }, [fetchLive]);

  const daily = data?.daily ?? [];
  const latest = daily[daily.length - 1];
  const profile = data?.profile ?? [];
  const maxProfile = Math.max(0.01, ...profile.map((p) => p.kwh));
  const maxDaily = Math.max(0.01, ...daily.map((d) => d.elec_kwh + d.gas_kwh));

  return (
    <Takeover onClose={onClose} accent="var(--control)" accentText="var(--ink)" title="Energy">
      <div className="h-full overflow-y-auto p-5 flex flex-col gap-5">
        {!data ? (
          <div className="flex-1 flex items-center justify-center" style={{ color: "var(--ink-30)" }}>
            Loading energy data…
          </div>
        ) : data.status !== "ok" || !latest ? (
          <div className="flex-1 flex items-center justify-center" style={{ color: "var(--ink-30)" }}>
            Energy data unavailable
          </div>
        ) : (
          <>
            {/* Stat tiles */}
            <div className="flex gap-3 shrink-0">
              <StatTile
                label="Right now"
                value={
                  liveW == null ? "—" : liveW >= 1000 ? `${(liveW / 1000).toFixed(1)}kW` : `${liveW}W`
                }
              />
              <StatTile
                label="Electricity"
                value={`${latest.elec_kwh.toFixed(1)} kWh`}
                sub={`£${latest.elec_cost.toFixed(2)} · ${latest.dayLabel}`}
              />
              <StatTile
                label="Gas"
                value={`${latest.gas_kwh.toFixed(1)} kWh`}
                sub={`£${latest.gas_cost.toFixed(2)} · ${latest.dayLabel}`}
              />
              <StatTile label="Day total" value={`£${latest.total_cost.toFixed(2)}`} sub={latest.ev ? "⚡ EV charge day" : " "} />
            </div>

            {/* Half-hourly profile */}
            {profile.length > 0 && (
              <div className="card-v2 p-4 shrink-0">
                <div
                  className="mb-2 uppercase"
                  style={{
                    fontFamily: "var(--font-display), sans-serif",
                    fontWeight: 700,
                    fontSize: 13,
                    letterSpacing: "0.06em",
                    color: "var(--text-mid)",
                  }}
                >
                  Through the day — {data.profileDateLabel}
                </div>
                <div className="flex items-end gap-[2px]" style={{ height: 130 }}>
                  {profile.map((p, i) => (
                    <div
                      key={i}
                      className="flex-1"
                      style={{
                        height: `${Math.max(2, (p.kwh / maxProfile) * 100)}%`,
                        background: p.kwh > maxProfile * 0.6 ? "var(--meals)" : "var(--control)",
                        borderRadius: 3,
                        minWidth: 0,
                      }}
                      title={`${p.time} — ${p.kwh.toFixed(2)} kWh`}
                    />
                  ))}
                </div>
                <div className="flex justify-between text-xs mt-1" style={{ color: "var(--text-dim)" }}>
                  <span>midnight</span>
                  <span>06:00</span>
                  <span>midday</span>
                  <span>18:00</span>
                  <span>midnight</span>
                </div>
              </div>
            )}

            {/* 14-day history */}
            <div className="card-v2 p-4 shrink-0">
              <div
                className="mb-2 uppercase flex items-center justify-between"
                style={{
                  fontFamily: "var(--font-display), sans-serif",
                  fontWeight: 700,
                  fontSize: 13,
                  letterSpacing: "0.06em",
                  color: "var(--text-mid)",
                }}
              >
                <span>Last {daily.length} days</span>
                <span className="flex items-center gap-3 normal-case" style={{ letterSpacing: 0 }}>
                  <span className="flex items-center gap-1">
                    <span style={{ width: 10, height: 10, borderRadius: 3, background: "var(--control)", display: "inline-block" }} />
                    electric
                  </span>
                  <span className="flex items-center gap-1">
                    <span style={{ width: 10, height: 10, borderRadius: 3, background: "var(--meals)", display: "inline-block" }} />
                    gas
                  </span>
                </span>
              </div>
              <div className="flex items-end gap-2" style={{ height: 150 }}>
                {daily.map((d) => (
                  <div key={d.date} className="flex-1 flex flex-col items-center justify-end h-full gap-1">
                    <span className="text-[11px] font-bold" style={{ color: "var(--text-mid)", fontVariantNumeric: "tabular-nums" }}>
                      £{d.total_cost.toFixed(0)}
                    </span>
                    <div className="w-full flex flex-col justify-end" style={{ flex: 1 }}>
                      <div
                        style={{
                          height: `${(d.gas_kwh / maxDaily) * 100}%`,
                          background: "var(--meals)",
                          borderRadius: "4px 4px 0 0",
                          opacity: 0.85,
                        }}
                      />
                      <div
                        style={{
                          height: `${(d.elec_kwh / maxDaily) * 100}%`,
                          background: "var(--control)",
                          borderRadius: d.gas_kwh > 0 ? "0 0 3px 3px" : 4,
                        }}
                      />
                    </div>
                    <span className="text-[11px]" style={{ color: d.ev ? "var(--chris)" : "var(--text-dim)" }}>
                      {d.ev ? "⚡" : ""}
                      {d.dayLabel[0]}
                      <span className="opacity-60">{d.dayNum}</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </Takeover>
  );
}
