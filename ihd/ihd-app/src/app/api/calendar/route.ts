import { NextRequest, NextResponse } from "next/server";

// Hadley API (Peterbot) — runs on the same machine as the dashboard dev server,
// or accessible from the Pi via the local network
const HADLEY_API = process.env.HADLEY_API_URL || "http://localhost:8100";

export async function GET(request: NextRequest) {
  const view = request.nextUrl.searchParams.get("view") || "week";
  const eventId = request.nextUrl.searchParams.get("id");

  try {
    let url: string;

    if (eventId) {
      url = `${HADLEY_API}/calendar/event?id=${encodeURIComponent(eventId)}`;
    } else if (view === "today") {
      url = `${HADLEY_API}/calendar/today`;
    } else {
      // Use /calendar/range for richer data (id, description, end)
      const today = new Date();
      const startDate = today.toISOString().slice(0, 10);
      const end = new Date(today);
      end.setDate(end.getDate() + 7);
      const endDate = end.toISOString().slice(0, 10);
      url = `${HADLEY_API}/calendar/range?start_date=${startDate}&end_date=${endDate}`;
    }

    const res = await fetch(url, {
      signal: AbortSignal.timeout(5000),
      cache: "no-store",
    });

    if (!res.ok) throw new Error(`Hadley API returned ${res.status}`);

    const data = await res.json();

    // Transform /calendar/range flat list into events_by_day format
    if (!eventId && view === "week" && data.events) {
      const eventsByDay: Record<string, unknown[]> = {};
      for (const ev of data.events) {
        const dateStr = (ev.start || "").slice(0, 10);
        if (!eventsByDay[dateStr]) eventsByDay[dateStr] = [];
        const allDay = !ev.start.includes("T");
        eventsByDay[dateStr].push({
          id: ev.id,
          title: ev.summary || ev.title,
          start: ev.start,
          end: ev.end,
          location: ev.location || null,
          all_day: allDay,
          calendar: ev.calendar,
          description: ev.description || null,
        });
      }
      return NextResponse.json({
        events_by_day: eventsByDay,
        total_events: data.count || data.events.length,
      });
    }

    return NextResponse.json(data);
  } catch (e) {
    return NextResponse.json(
      { error: "Calendar unavailable", detail: String(e) },
      { status: 200 }
    );
  }
}
