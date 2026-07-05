"use client";

import { useEffect, useState } from "react";
import Modal from "@/components/ui/Modal";

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

interface EventDetail {
  id: string;
  summary: string;
  start: string;
  end: string;
  location: string;
  description: string;
  status: string;
  link: string;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}

function duration(start: string, end?: string): string | null {
  if (!end) return null;
  const ms = new Date(end).getTime() - new Date(start).getTime();
  const mins = Math.round(ms / 60000);
  if (mins < 60) return `${mins} min`;
  const hrs = Math.floor(mins / 60);
  const remMins = mins % 60;
  return remMins > 0 ? `${hrs}h ${remMins}m` : `${hrs}h`;
}

function linkify(text: string) {
  const urlRegex = /(https?:\/\/[^\s]+)/g;
  const parts = text.split(urlRegex);
  return parts.map((part, i) =>
    urlRegex.test(part) ? (
      <span key={i} style={{ color: "var(--calendar)" }} className="break-all">
        {part}
      </span>
    ) : (
      <span key={i}>{part}</span>
    )
  );
}

export default function EventPopup({
  event,
  onClose,
}: {
  event: CalEvent;
  onClose: () => void;
}) {
  const c = PERSON_COLOURS[event.calendar] || "var(--ink-30)";
  const [detail, setDetail] = useState<EventDetail | null>(null);

  // Fetch full event detail for complete description
  useEffect(() => {
    if (!event.id) return;
    fetch(`/api/calendar?id=${encodeURIComponent(event.id)}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data && !data.error) setDetail(data);
      })
      .catch(() => {});
  }, [event.id]);

  // Use detail data when available, fall back to event data
  const description = detail?.description || event.description || "";
  const location = detail?.location || event.location || "";
  const endTime = detail?.end || event.end;

  return (
    <Modal onClose={onClose} accent="var(--calendar)" title={event.title}>
      <div className="px-5 pt-4 flex flex-col gap-4">
        {/* Who */}
        <div>
          <span
            className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wide"
            style={{
              color: c,
              border: `1.5px solid ${c}`,
              background: "var(--surface-alt)",
            }}
          >
            {event.calendar}
          </span>
        </div>

        {/* Time */}
        <div
          className="flex items-center gap-3 p-3 rounded-xl"
          style={{ background: "var(--calendar-tint)" }}
        >
          <span className="text-xl" aria-hidden>
            🕐
          </span>
          <div>
            {event.all_day ? (
              <div
                className="text-base font-bold"
                style={{ fontFamily: "var(--font-display), sans-serif" }}
              >
                All day
              </div>
            ) : (
              <>
                <div
                  className="text-base font-bold"
                  style={{
                    fontFamily: "var(--font-display), sans-serif",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {formatTime(event.start)}
                  {endTime && ` — ${formatTime(endTime)}`}
                </div>
                {endTime && (
                  <div className="text-xs mt-0.5" style={{ color: "var(--ink-60)" }}>
                    {duration(event.start, endTime)}
                  </div>
                )}
              </>
            )}
            <div className="text-xs mt-0.5" style={{ color: "var(--ink-60)" }}>
              {event.all_day ? formatDate(event.start + "T00:00:00") : formatDate(event.start)}
            </div>
          </div>
        </div>

        {/* Location */}
        {location && (
          <div
            className="flex items-center gap-3 p-3 rounded-xl"
            style={{ background: "var(--surface-alt)" }}
          >
            <span className="text-xl" aria-hidden>
              📍
            </span>
            <div className="text-base">{location}</div>
          </div>
        )}

        {/* Description */}
        {description && (
          <div className="p-3 rounded-xl" style={{ background: "var(--surface-alt)" }}>
            <div
              className="text-xs font-bold uppercase tracking-widest mb-2"
              style={{ color: "var(--ink-60)" }}
            >
              Notes
            </div>
            <div
              className="text-base leading-relaxed whitespace-pre-wrap"
              style={{ color: "var(--ink-60)" }}
            >
              {linkify(description)}
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
