import { NextResponse } from "next/server";

// Hadley API on the main PC — daily summaries including PROVISIONAL rows
// synthesised from Octopus Home Mini telemetry when the official DCC
// half-hourly feed lags (electricity only; gas has no Mini telemetry).
const HADLEY_SUMMARY = "http://192.168.0.87:8100/energy/summary?days=3";

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
  is_ev_charge_day: boolean | null;
  provisional?: boolean;
}

function formatDate(iso: string): string {
  // Format: "Sun 8 Mar"
  return new Date(iso + "T12:00:00Z").toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "Europe/London",
  });
}

function buildResponse(rows: DailySummary[]) {
  if (!rows.length) {
    return NextResponse.json({ status: "no_data" }, { status: 200 });
  }

  // Latest row per fuel — elec may lead gas by a day or two because
  // provisional elec rows exist while gas waits on the official feed.
  const elec = rows.find((r) => r.fuel_type === "electricity");
  const gas = rows.find((r) => r.fuel_type === "gas");
  const latestDate = elec?.summary_date ?? rows[0].summary_date;

  return NextResponse.json({
    status: "ok",
    dateLabel: formatDate(latestDate),
    estimated: elec?.provisional ?? false,
    electricity: {
      kwh: Math.round((elec?.total_kwh ?? 0) * 10) / 10,
      cost_pounds: Math.round(elec?.total_cost_pence ?? 0) / 100,
    },
    gas: {
      kwh: Math.round((gas?.total_kwh ?? 0) * 10) / 10,
      cost_pounds: Math.round(gas?.total_cost_pence ?? 0) / 100,
      dateLabel:
        gas && gas.summary_date !== latestDate
          ? formatDate(gas.summary_date)
          : null,
    },
    isEvDay: elec?.is_ev_charge_day ?? false,
  });
}

async function fromHadleyApi() {
  const res = await fetch(HADLEY_SUMMARY, {
    signal: AbortSignal.timeout(5000),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Hadley API returned ${res.status}`);
  const data: { days: DailySummary[] } = await res.json();
  return buildResponse(data.days ?? []);
}

async function fromSupabase() {
  // Fallback: official complete days only (no provisional rows).
  const res = await fetch(
    `${SUPABASE_URL}/rest/v1/energy_daily_summary?order=summary_date.desc&limit=6`,
    {
      headers: SB_HEADERS,
      signal: AbortSignal.timeout(5000),
      cache: "no-store",
    }
  );
  if (!res.ok) throw new Error(`Supabase returned ${res.status}`);
  const rows: DailySummary[] = await res.json();
  return buildResponse(rows);
}

export async function GET() {
  try {
    return await fromHadleyApi();
  } catch {
    // Hadley API (main PC) unreachable — fall back to Supabase direct.
  }
  try {
    return await fromSupabase();
  } catch {
    return NextResponse.json(
      {
        status: "offline",
        dateLabel: null,
        estimated: false,
        electricity: { kwh: 0, cost_pounds: 0 },
        gas: { kwh: 0, cost_pounds: 0, dateLabel: null },
        isEvDay: false,
      },
      { status: 200 }
    );
  }
}
