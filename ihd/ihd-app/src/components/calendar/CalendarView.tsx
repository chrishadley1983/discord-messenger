"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Card } from "@/components/ui/Card";
import EventPopup from "./EventPopup";

const PERSON_COLOURS: Record<string, string> = {
  Chris: "var(--chris)",
  Abby: "var(--abby)",
  Max: "var(--max)",
  Emmie: "var(--emmie)",
  Family: "var(--family)",
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

interface WeekData {
  events_by_day: Record<string, CalEvent[]>;
  total_events: number;
}

function formatTime(iso: string, allDay: boolean): string {
  if (allDay) return "All day";
  const d = new Date(iso);
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function formatDayLabel(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);

  if (d.getTime() === today.getTime()) return "Today";
  if (d.getTime() === tomorrow.getTime()) return "Tomorrow";
  return d.toLocaleDateString("en-GB", { weekday: "long" });
}

function formatDateSub(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
  });
}

function isPast(event: CalEvent): boolean {
  if (event.all_day) return false;
  return new Date(event.start) < new Date();
}

function Pill({ who }: { who: string }) {
  const c = PERSON_COLOURS[who] || "var(--ink-30)";
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold uppercase tracking-wide"
      style={{
        color: c,
        border: `1.5px solid ${c}`,
        background: "var(--surface-alt)",
      }}
    >
      {who}
    </span>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="flex-1 flex items-center justify-center text-center px-3 py-6">
      <div
        className="font-bold text-base leading-snug"
        style={{ fontFamily: "var(--font-display), sans-serif", color: "var(--ink-60)" }}
      >
        {text}
      </div>
    </div>
  );
}

function EventRow({
  event,
  onSelect,
  large,
}: {
  event: CalEvent;
  onSelect: (e: CalEvent) => void;
  large?: boolean;
}) {
  const past = isPast(event);
  const c = PERSON_COLOURS[event.calendar] || "var(--ink-30)";

  return (
    <button
      onClick={() => onSelect(event)}
      className="pressable flex items-center gap-3 w-full text-left border-none cursor-pointer rounded-xl transition-colors hover:bg-[var(--calendar-tint)]"
      style={{
        background: "transparent",
        borderLeft: `4px solid ${c}`,
        minHeight: 56,
        padding: large ? "12px 14px" : "10px 12px",
        opacity: past ? 0.4 : 1,
      }}
    >
      <div
        className={`shrink-0 font-bold ${large ? "text-lg" : "text-base"}`}
        style={{
          fontFamily: "var(--font-display), sans-serif",
          fontVariantNumeric: "tabular-nums",
          minWidth: large ? 68 : 58,
          textDecoration: past ? "line-through" : "none",
        }}
      >
        {formatTime(event.start, event.all_day)}
      </div>
      <div className="flex-1 min-w-0">
        <div
          className={`font-semibold line-clamp-2 ${large ? "text-lg" : "text-base"}`}
          style={{ textDecoration: past ? "line-through" : "none" }}
        >
          {event.title}
        </div>
        <div className="flex items-center gap-2 mt-1">
          <Pill who={event.calendar} />
          {event.location && (
            <span className="text-xs truncate" style={{ color: "var(--ink-60)" }}>
              📍 {event.location}
            </span>
          )}
        </div>
      </div>
    </button>
  );
}

function DayColumn({
  dateStr,
  events,
  isMain,
  standalone,
  emptyText,
  onSelectEvent,
}: {
  dateStr: string;
  events: CalEvent[];
  isMain: boolean;
  standalone: boolean;
  emptyText: string;
  onSelectEvent: (e: CalEvent) => void;
}) {
  const label = formatDayLabel(dateStr);

  return (
    <Card
      section="calendar"
      chip={label}
      tinted={isMain}
      headerRight={
        <span
          className="text-xs font-bold"
          style={{ fontFamily: "var(--font-display), sans-serif", color: "var(--ink-60)" }}
        >
          {events.length} event{events.length !== 1 ? "s" : ""}
        </span>
      }
      className={`flex flex-col ${standalone ? "flex-1 min-h-0" : "flex-shrink-0"}`}
    >
      <div
        className="text-xs font-bold mb-2"
        style={{
          fontFamily: "var(--font-display), sans-serif",
          color: "var(--ink-60)",
          letterSpacing: "0.02em",
        }}
      >
        {formatDateSub(dateStr)}
      </div>

      <div
        className={`flex flex-col gap-1.5 ${
          standalone ? "flex-1 min-h-0 overflow-y-auto" : ""
        }`}
      >
        {events.length === 0 ? (
          <EmptyState text={emptyText} />
        ) : (
          events.map((ev) => (
            <EventRow key={ev.id} event={ev} onSelect={onSelectEvent} large={isMain} />
          ))
        )}
      </div>
    </Card>
  );
}

export default function CalendarView() {
  const [data, setData] = useState<WeekData | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<CalEvent | null>(null);
  const restColRef = useRef<HTMLDivElement>(null);
  const [restOverflow, setRestOverflow] = useState(false);

  const checkRestOverflow = useCallback(() => {
    const el = restColRef.current;
    if (el) setRestOverflow(el.scrollHeight > el.clientHeight + 2);
  }, []);

  const fetchCalendar = useCallback(async () => {
    try {
      const res = await fetch("/api/calendar?view=week");
      if (res.ok) {
        const d = await res.json();
        if (!d.error) setData(d);
      }
    } catch {
      // keep last known
    }
  }, []);

  useEffect(() => {
    fetchCalendar();
    const t = setInterval(fetchCalendar, 10 * 60 * 1000); // 10 min
    return () => clearInterval(t);
  }, [fetchCalendar]);

  useEffect(() => {
    checkRestOverflow();
    window.addEventListener("resize", checkRestOverflow);
    return () => window.removeEventListener("resize", checkRestOverflow);
  }, [data, checkRestOverflow]);

  if (!data) {
    return (
      <div className="flex items-center justify-center h-full">
        <div
          className="font-bold text-lg"
          style={{ fontFamily: "var(--font-display), sans-serif", color: "var(--ink-60)" }}
        >
          Loading calendar…
        </div>
      </div>
    );
  }

  // Sort dates and split into today, tomorrow, and rest of week
  const dates = Object.keys(data.events_by_day).sort();
  const todayStr = new Date().toISOString().slice(0, 10);
  const tomorrowStr = new Date(Date.now() + 86400000).toISOString().slice(0, 10);

  const todayEvents = data.events_by_day[todayStr] || [];
  const tomorrowEvents = data.events_by_day[tomorrowStr] || [];
  // Only upcoming days — the API's week window can include already-past days
  const restDates = dates.filter((d) => d > tomorrowStr);

  return (
    <div className="h-full flex flex-col">
      <div className="flex-1 min-h-0 pt-3 flex gap-3 stagger-in">
        {/* Left column — Today (bigger, tinted) */}
        <div className="flex-[2] min-w-0 flex flex-col">
          <DayColumn
            dateStr={todayStr}
            events={todayEvents}
            isMain
            standalone
            emptyText="Nothing on — free day! 🎉"
            onSelectEvent={setSelectedEvent}
          />
        </div>

        {/* Middle column — Tomorrow */}
        <div className="flex-[1.5] min-w-0 flex flex-col">
          <DayColumn
            dateStr={tomorrowStr}
            events={tomorrowEvents}
            isMain={false}
            standalone
            emptyText="Tomorrow's looking clear too! 🎉"
            onSelectEvent={setSelectedEvent}
          />
        </div>

        {/* Right column — Rest of week */}
        <div className="flex-[2] min-w-0 flex flex-col relative">
          <div
            ref={restColRef}
            onScroll={checkRestOverflow}
            className="flex-1 min-h-0 flex flex-col gap-3 overflow-y-auto"
            style={{ paddingBottom: 24 }}
          >
            {restDates.length === 0 ? (
              <Card section="calendar" className="flex-1 flex items-center justify-center">
                <EmptyState text="Rest of the week is wide open! 🎉" />
              </Card>
            ) : (
              restDates.map((dateStr) => (
                <DayColumn
                  key={dateStr}
                  dateStr={dateStr}
                  events={data.events_by_day[dateStr] || []}
                  isMain={false}
                  standalone={false}
                  emptyText="Nothing scheduled"
                  onSelectEvent={setSelectedEvent}
                />
              ))
            )}
          </div>
          {restOverflow && (
            <div
              aria-hidden
              className="pointer-events-none absolute bottom-0 left-0 right-0 flex items-end justify-center"
              style={{
                height: 44,
                background: "linear-gradient(to bottom, transparent, var(--surface))",
              }}
            >
              <span style={{ color: "var(--ink-30)", fontSize: 18, lineHeight: 1, marginBottom: 4 }}>▾</span>
            </div>
          )}
        </div>
      </div>

      {/* Event detail popup */}
      {selectedEvent && (
        <EventPopup event={selectedEvent} onClose={() => setSelectedEvent(null)} />
      )}
    </div>
  );
}
