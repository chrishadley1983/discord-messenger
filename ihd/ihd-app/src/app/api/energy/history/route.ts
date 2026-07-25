import { NextResponse } from "next/server";

/**
 * Energy history for the detail takeover:
 * - daily: last 14 days per fuel from energy_daily_summary
 * - profile: half-hourly electricity for the latest complete day
 */

const SUPABASE_URL = "https://modjoikyuhqzouxvieua.supabase.co";
const SUPABASE_KEY = process.env.SUPABASE_ANON_KEY || "";

const SB_HEADERS = {
  apikey: SUPABASE_KEY,
  Authorization: `Bearer ${SUPABASE_KEY}`,
};

interface DailyRow {
  summary_date: string;
  fuel_type: string;
  total_kwh: number;
  total_cost_pence: number;
  is_ev_charge_day: boolean;
}

interface HalfHourRow {
  interval_start: string;
  consumption_kwh: number;
}

export async function GET() {
  try {
    // Last 14 days, both fuels (28 rows max)
    const dailyRes = await fetch(
      `${SUPABASE_URL}/rest/v1/energy_daily_summary?order=summary_date.desc&limit=28`,
      { headers: SB_HEADERS, signal: AbortSignal.timeout(6000), cache: "no-store" }
    );
    if (!dailyRes.ok) throw new Error(`daily ${dailyRes.status}`);
    const rows: DailyRow[] = await dailyRes.json();
    if (!rows.length) return NextResponse.json({ status: "no_data" });

    // Group by date
    const byDate = new Map<
      string,
      { elec_kwh: number; elec_cost: number; gas_kwh: number; gas_cost: number; ev: boolean }
    >();
    for (const r of rows) {
      const d = byDate.get(r.summary_date) || {
        elec_kwh: 0,
        elec_cost: 0,
        gas_kwh: 0,
        gas_cost: 0,
        ev: false,
      };
      if (r.fuel_type === "electricity") {
        d.elec_kwh = r.total_kwh;
        d.elec_cost = r.total_cost_pence / 100;
        d.ev = d.ev || r.is_ev_charge_day;
      } else if (r.fuel_type === "gas") {
        d.gas_kwh = r.total_kwh;
        d.gas_cost = r.total_cost_pence / 100;
      }
      byDate.set(r.summary_date, d);
    }
    const daily = [...byDate.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([date, d]) => ({
        date,
        dayLabel: new Date(date + "T00:00:00Z").toLocaleDateString("en-GB", {
          weekday: "short",
          timeZone: "UTC",
        }),
        dayNum: new Date(date + "T00:00:00Z").getUTCDate(),
        ...d,
        total_cost: Math.round((d.elec_cost + d.gas_cost) * 100) / 100,
      }));

    // Half-hourly electricity for the latest complete day
    const latest = daily[daily.length - 1].date;
    const nextDay = new Date(new Date(latest + "T00:00:00Z").getTime() + 86400000)
      .toISOString()
      .slice(0, 10);
    const hhRes = await fetch(
      `${SUPABASE_URL}/rest/v1/energy_consumption?fuel_type=eq.electricity` +
        `&interval_start=gte.${latest}T00:00:00Z&interval_start=lt.${nextDay}T00:00:00Z` +
        `&select=interval_start,consumption_kwh&order=interval_start.asc`,
      { headers: SB_HEADERS, signal: AbortSignal.timeout(6000), cache: "no-store" }
    );
    let profile: { time: string; kwh: number }[] = [];
    if (hhRes.ok) {
      const hh: HalfHourRow[] = await hhRes.json();
      profile = hh.map((r) => ({
        time: new Date(r.interval_start).toLocaleTimeString("en-GB", {
          hour: "2-digit",
          minute: "2-digit",
          timeZone: "Europe/London",
        }),
        kwh: r.consumption_kwh,
      }));
    }

    const profileDateLabel = new Date(latest + "T00:00:00Z").toLocaleDateString("en-GB", {
      weekday: "long",
      day: "numeric",
      month: "long",
      timeZone: "UTC",
    });

    return NextResponse.json({ status: "ok", daily, profile, profileDateLabel });
  } catch {
    return NextResponse.json({ status: "offline" }, { status: 200 });
  }
}
