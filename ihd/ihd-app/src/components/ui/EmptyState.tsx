"use client";

/**
 * Shared empty/degraded-state pattern (challenge fix: empty states were
 * inconsistent — some cards had icon+headline+subtext, others bare grey text).
 * Always renders inside the card frame: icon, headline, optional subtext.
 */

import Icon from "./Icon";

export default function EmptyState({
  icon,
  headline,
  subtext,
  compact = false,
}: {
  /** Icon name from ui/Icon, or a ReactNode for bespoke art (e.g. the pet egg) */
  icon?: string | React.ReactNode;
  headline: string;
  subtext?: string;
  /** Tighter spacing for mini-cards */
  compact?: boolean;
}) {
  return (
    <div
      className="flex-1 flex flex-col items-center justify-center text-center"
      style={{ padding: compact ? 8 : 20, minHeight: 0 }}
    >
      {icon != null && (
        <div style={{ color: "var(--ink-30)", marginBottom: compact ? 4 : 10 }}>
          {typeof icon === "string" ? <Icon name={icon} size={compact ? 22 : 32} /> : icon}
        </div>
      )}
      <div
        style={{
          fontFamily: "var(--font-display), sans-serif",
          fontWeight: 700,
          fontSize: compact ? 15 : 19,
          color: "var(--ink-60)",
        }}
      >
        {headline}
      </div>
      {subtext && (
        <div
          className="mt-1"
          style={{
            fontFamily: "var(--font-body), sans-serif",
            fontSize: compact ? 13 : 15,
            color: "var(--ink-30)",
          }}
        >
          {subtext}
        </div>
      )}
    </div>
  );
}
