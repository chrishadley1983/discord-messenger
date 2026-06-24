import { NextResponse } from "next/server";

const SUPABASE_URL = "https://modjoikyuhqzouxvieua.supabase.co";
const SUPABASE_KEY = process.env.SUPABASE_ANON_KEY || "";

const SB_HEADERS = {
  apikey: SUPABASE_KEY,
  Authorization: `Bearer ${SUPABASE_KEY}`,
};

interface DailySummary {
  summary_date: string;
  fuel_type: string;
  total_kwh: number;
  total_cost_pence: number;
  is_ev_charge_day: boolean;
}

export async function GET() {
  try {
    // Get latest rows from energy_daily_summary (complete days only)
    const res = await fetch(
      `${SUPABASE_URL}/rest/v1/energy_daily_summary?order=summary_date.desc&limit=4`,
      {
        headers: SB_HEADERS,
        signal: AbortSignal.timeout(5000),
        cache: "no-store",
      }
    );

    if (!res.ok) throw new Error(`Supabase returned ${res.status}`);

    const rows: DailySummary[] = await res.json();
    if (!rows.length) {
      return NextResponse.json({ status: "no_data" }, { status: 200 });
    }

    // Most recent complete day
    const latestDate = rows[0].summary_date;
    const elec = rows.find(
      (r) => r.summary_date === latestDate && r.fuel_type === "electricity"
    );
    const gas = rows.find(
      (r) => r.summary_date === latestDate && r.fuel_type === "gas"
    );

    // Format: "Sun 8 Mar"
    const d = new Date(latestDate + "T12:00:00Z");
    const dateLabel = d.toLocaleDateString("en-GB", {
      weekday: "short",
      day: "numeric",
      month: "short",
      timeZone: "Europe/London",
    });

    return NextResponse.json({
      status: "ok",
      dateLabel,
      electricity: {
        kwh: Math.round((elec?.total_kwh ?? 0) * 10) / 10,
        cost_pounds: Math.round(elec?.total_cost_pence ?? 0) / 100,
      },
      gas: {
        kwh: Math.round((gas?.total_kwh ?? 0) * 10) / 10,
        cost_pounds: Math.round(gas?.total_cost_pence ?? 0) / 100,
      },
      isEvDay: elec?.is_ev_charge_day ?? false,
    });
  } catch {
    return NextResponse.json(
      {
        status: "offline",
        dateLabel: null,
        electricity: { kwh: 0, cost_pounds: 0 },
        gas: { kwh: 0, cost_pounds: 0 },
        isEvDay: false,
      },
      { status: 200 }
    );
  }
}
