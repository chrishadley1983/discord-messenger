"use client";

import { useEffect, useRef, useState } from "react";

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
      <span key={i} className="text-accent break-all">
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
  const overlayRef = useRef<HTMLDivElement>(null);
  const c = PERSON_COLOURS[event.calendar] || "#888";
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

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  // Use detail data when available, fall back to event data
  const description = detail?.description || event.description || "";
  const location = detail?.location || event.location || "";
  const endTime = detail?.end || event.end;

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
      style={{ background: "rgba(26, 23, 16, 0.4)" }}
    >
      <div
        className="bg-surface rounded-2xl shadow-xl w-[520px] max-h-[80vh] overflow-y-auto"
        style={{ borderTop: `4px solid ${c}` }}
      >
        {/* Header */}
        <div className="p-6 pb-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <div className="text-xl font-semibold leading-tight">
                {event.title}
              </div>
              <div className="flex items-center gap-2 mt-2">
                <span
                  className="inline-block px-2.5 py-0.5 rounded-full text-sm font-bold uppercase tracking-wide"
                  style={{
                    background: c + "22",
                    color: c,
                    border: `1px solid ${c}44`,
                  }}
                >
                  {event.calendar}
                </span>
              </div>
            </div>
            <button
              onClick={onClose}
              className="text-text-dim hover:text-text text-xl cursor-pointer bg-transparent border-none p-1"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Details */}
        <div className="px-6 pb-6 flex flex-col gap-4">
          {/* Time */}
          <div className="flex items-center gap-3 p-3 bg-surface-alt rounded-xl">
            <span className="text-lg">🕐</span>
            <div>
              {event.all_day ? (
                <div className="text-sm font-medium">All day</div>
              ) : (
                <>
                  <div className="text-sm font-medium">
                    {formatTime(event.start)}
                    {endTime && ` — ${formatTime(endTime)}`}
                  </div>
                  {endTime && (
                    <div className="text-sm text-text-mid mt-0.5">
                      {duration(event.start, endTime)}
                    </div>
                  )}
                </>
              )}
              <div className="text-sm text-text-mid mt-0.5">
                {event.all_day
                  ? formatDate(event.start + "T00:00:00")
                  : formatDate(event.start)}
              </div>
            </div>
          </div>

          {/* Location */}
          {location && (
            <div className="flex items-center gap-3 p-3 bg-surface-alt rounded-xl">
              <span className="text-lg">📍</span>
              <div className="text-sm">{location}</div>
            </div>
          )}

          {/* Description */}
          {description && (
            <div className="p-3 bg-surface-alt rounded-xl">
              <div className="text-xs font-bold uppercase tracking-widest text-text-mid mb-2">
                Notes
              </div>
              <div className="text-sm text-text-mid leading-relaxed whitespace-pre-wrap">
                {linkify(description)}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
