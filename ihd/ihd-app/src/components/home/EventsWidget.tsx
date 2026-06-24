"use client";

import { useState, useEffect, useCallback } from "react";
import EventPopup from "../calendar/EventPopup";

const PERSON_COLOURS: Record<string, string> = {
  Chris: "#c47f0a",
  Abby: "#c8304c",
  Max: "#2060b8",
  Emmie: "#7040b8",
  Family: "#1e8a50",
};

interface CalEvent {
  id: string;
  title: string;
  start: string;
  end?: string;
  location: string | null;
  all_day: boolean;
  calendar: string;
  description?: string;
}

function Pill({ who }: { who: string }) {
  const c = PERSON_COLOURS[who] || "#888";
  return (
    <span
      className="inline-block px-2 py-0.5 rounded-full text-xs font-bold uppercase tracking-wide"
      style={{
        background: c + "22",
        color: c,
        border: `1px solid ${c}44`,
      }}
    >
      {who}
    </span>
  );
}

function formatTime(iso: string, allDay: boolean): string {
  if (allDay) return "All day";
  const d = new Date(iso);
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function isPast(event: CalEvent): boolean {
  if (event.all_day) return false;
  return new Date(event.start) < new Date();
}

export default function EventsWidget() {
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedEvent, setSelectedEvent] = useState<CalEvent | null>(null);

  const fetchEvents = useCallback(async () => {
    try {
      const res = await fetch("/api/calendar?view=today");
      if (res.ok) {
        const data = await res.json();
        if (data.events) {
          setEvents(data.events);
        }
      }
    } catch {
      // keep last known
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEvents();
    const t = setInterval(fetchEvents, 10 * 60 * 1000); // 10 min
    return () => clearInterval(t);
  }, [fetchEvents]);

  return (
    <>
      <div className="bg-surface border border-border rounded-2xl p-4 shadow-sm flex-1 flex flex-col min-h-0">
        <div className="text-xs font-bold uppercase tracking-widest text-text-mid mb-2.5">
          Today&apos;s Events
        </div>
        <div className="flex-1 overflow-y-auto overflow-x-hidden flex flex-col gap-2.5">
          {loading ? (
            <div className="text-xs text-text-dim text-center py-4">
              Loading...
            </div>
          ) : events.length === 0 ? (
            <div className="text-xs text-text-dim text-center py-4">
              Nothing scheduled today
            </div>
          ) : (
            events.map((ev) => {
              const past = isPast(ev);
              const c = PERSON_COLOURS[ev.calendar] || "#888";
              return (
                <button
                  key={ev.id}
                  onClick={() => setSelectedEvent(ev)}
                  className="flex gap-2.5 items-start text-left border-none cursor-pointer bg-transparent rounded-lg p-1 -m-1 hover:bg-surface-alt transition-colors"
                  style={{
                    opacity: past ? 0.4 : 1,
                    borderLeft: `2px solid ${c}`,
                    paddingLeft: 8,
                  }}
                >
                  <div
                    className="text-sm font-semibold text-text-mid min-w-[42px] pt-0.5"
                    style={{
                      textDecoration: past ? "line-through" : "none",
                    }}
                  >
                    {formatTime(ev.start, ev.all_day)}
                  </div>
                  <div>
                    <div className="text-sm font-medium mb-1">{ev.title}</div>
                    <Pill who={ev.calendar} />
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      {selectedEvent && (
        <EventPopup
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
        />
      )}
    </>
  );
}
