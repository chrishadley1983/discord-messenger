"use client";

import { useState, useEffect, useCallback } from "react";
import EventPopup from "../calendar/EventPopup";
import { Card } from "../ui/Card";
import Icon from "../ui/Icon";

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
      className="inline-flex items-center px-2.5 py-1 rounded-full text-sm font-bold uppercase tracking-wide"
      style={{
        background: "var(--surface)",
        color: c,
        border: `2px solid ${c}`,
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
      // Fetch the same week window the Calendar screen uses, then derive
      // today's events client-side — keeps the two screens agreed on
      // times/past-status instead of trusting a separate ?view=today path.
      const res = await fetch("/api/calendar?view=week");
      if (res.ok) {
        const data = await res.json();
        if (data.events_by_day) {
          const todayStr = new Date().toISOString().slice(0, 10);
          setEvents(data.events_by_day[todayStr] || []);
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
      <Card section="calendar" chip="Today's Events" chipIcon={<Icon name="calendar" size={16} />} className="flex-1 min-h-0">
        <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden flex flex-col gap-2">
          {loading ? (
            <div className="text-base text-ink/60 text-center py-4">
              Loading...
            </div>
          ) : events.length === 0 ? (
            <div className="text-base text-ink/60 text-center py-4">
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
                  className="pressable shrink-0 flex gap-3 items-start text-left border-none cursor-pointer bg-transparent rounded-xl p-2 hover:bg-[var(--calendar-tint)] transition-colors"
                  style={{
                    minHeight: 56,
                    opacity: past ? 0.45 : 1,
                    borderLeft: `3px solid ${c}`,
                  }}
                >
                  <div
                    className="text-base font-semibold text-ink/60 min-w-[52px] pt-0.5"
                    style={{
                      fontFamily: "var(--font-display), sans-serif",
                      textDecoration: past ? "line-through" : "none",
                    }}
                  >
                    {formatTime(ev.start, ev.all_day)}
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <div className="text-base font-semibold leading-tight">{ev.title}</div>
                    <Pill who={ev.calendar} />
                  </div>
                </button>
              );
            })
          )}
        </div>
      </Card>

      {selectedEvent && (
        <EventPopup
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
        />
      )}
    </>
  );
}
