"use client";

import { useState, useEffect, useCallback } from "react";
import EventPopup from "./EventPopup";

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

function isWeekend(dateStr: string): boolean {
  const d = new Date(dateStr + "T00:00:00");
  return d.getDay() === 0 || d.getDay() === 6;
}

function isToday(dateStr: string): boolean {
  return dateStr === new Date().toISOString().slice(0, 10);
}

function isPast(event: CalEvent): boolean {
  if (event.all_day) return false;
  return new Date(event.start) < new Date();
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
  const c = PERSON_COLOURS[event.calendar] || "#888";

  return (
    <button
      onClick={() => onSelect(event)}
      className={`flex items-start gap-3 w-full text-left border-none cursor-pointer rounded-xl transition-colors ${
        large ? "p-3" : "p-2.5"
      } ${past ? "opacity-40" : ""} hover:bg-surface-alt active:scale-[0.99]`}
      style={{
        background: "transparent",
        borderLeft: `3px solid ${c}`,
      }}
    >
      <div
        className={`${large ? "text-sm" : "text-xs"} font-semibold text-text-mid min-w-[50px] pt-0.5`}
        style={{ textDecoration: past ? "line-through" : "none" }}
      >
        {formatTime(event.start, event.all_day)}
      </div>
      <div className="flex-1 min-w-0">
        <div
          className={`${large ? "text-[15px]" : "text-sm"} font-medium truncate`}
        >
          {event.title}
        </div>
        <div className="flex items-center gap-2 mt-1">
          <Pill who={event.calendar} />
          {event.location && (
            <span className="text-xs text-text-dim truncate">
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
  onSelectEvent,
}: {
  dateStr: string;
  events: CalEvent[];
  isMain: boolean;
  onSelectEvent: (e: CalEvent) => void;
}) {
  const weekend = isWeekend(dateStr);
  const today = isToday(dateStr);

  return (
    <div
      className={`bg-surface border rounded-2xl shadow-sm flex flex-col overflow-hidden ${
        today
          ? "border-accent"
          : weekend
          ? "border-purple/30"
          : "border-border"
      }`}
    >
      {/* Day header */}
      <div
        className={`px-4 py-3 border-b border-border ${
          today ? "bg-accent-glow" : weekend ? "bg-purple/5" : ""
        }`}
      >
        <div
          className={`${isMain ? "text-lg" : "text-sm"} font-semibold ${
            today ? "text-accent" : ""
          }`}
        >
          {formatDayLabel(dateStr)}
        </div>
        <div className="text-sm text-text-mid">{formatDateSub(dateStr)}</div>
        <div className="text-xs text-text-dim mt-1">
          {events.length} event{events.length !== 1 ? "s" : ""}
        </div>
      </div>

      {/* Events */}
      <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-1">
        {events.length === 0 ? (
          <div className="text-xs text-text-dim text-center py-6">
            Nothing scheduled
          </div>
        ) : (
          events.map((ev) => (
            <EventRow
              key={ev.id}
              event={ev}
              onSelect={onSelectEvent}
              large={isMain}
            />
          ))
        )}
      </div>
    </div>
  );
}

export default function CalendarView() {
  const [data, setData] = useState<WeekData | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<CalEvent | null>(null);

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

  if (!data) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-text-mid text-sm">Loading calendar...</div>
      </div>
    );
  }

  // Sort dates and split into today, tomorrow, and rest of week
  const dates = Object.keys(data.events_by_day).sort();
  const todayStr = new Date().toISOString().slice(0, 10);
  const tomorrowStr = new Date(Date.now() + 86400000).toISOString().slice(0, 10);

  const todayEvents = data.events_by_day[todayStr] || [];
  const tomorrowEvents = data.events_by_day[tomorrowStr] || [];
  const restDates = dates.filter((d) => d !== todayStr && d !== tomorrowStr);

  return (
    <div className="h-full pt-3 flex gap-3" style={{ animation: "fadeIn .2s ease both" }}>
      {/* Left column — Today (bigger) */}
      <div className="flex-[2] min-w-0">
        <DayColumn
          dateStr={todayStr}
          events={todayEvents}
          isMain={true}
          onSelectEvent={setSelectedEvent}
        />
      </div>

      {/* Middle column — Tomorrow */}
      <div className="flex-[1.5] min-w-0">
        <DayColumn
          dateStr={tomorrowStr}
          events={tomorrowEvents}
          isMain={false}
          onSelectEvent={setSelectedEvent}
        />
      </div>

      {/* Right column — Rest of week */}
      <div className="flex-[2] min-w-0 flex flex-col gap-3">
        {restDates.length === 0 ? (
          <div className="bg-surface border border-border rounded-2xl shadow-sm flex items-center justify-center flex-1">
            <div className="text-xs text-text-dim">No more events this week</div>
          </div>
        ) : (
          restDates.map((dateStr) => (
            <DayColumn
              key={dateStr}
              dateStr={dateStr}
              events={data.events_by_day[dateStr] || []}
              isMain={false}
              onSelectEvent={setSelectedEvent}
            />
          ))
        )}
      </div>

      {/* Event detail popup */}
      {selectedEvent && (
        <EventPopup
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
        />
      )}
    </div>
  );
}
