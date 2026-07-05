"use client";

/**
 * Sticker-card primitives (DESIGN_SPEC_V2 §3).
 *
 * <Card section="kids" chip="Pocket Money" chipIcon="💰"> ... </Card>
 * Section colours: home | calendar | meals | kids | media | control | hb
 * (ink text on marigold/mint; white text on the rest)
 */

import type { CSSProperties, ReactNode } from "react";

export type Section =
  | "home"
  | "calendar"
  | "meals"
  | "kids"
  | "media"
  | "control"
  | "hb";

/** Sections whose signature colour is light enough to need ink text */
const INK_TEXT_SECTIONS: Section[] = ["home", "control"];

export function sectionColor(section: Section): string {
  return `var(--${section})`;
}
export function sectionTint(section: Section): string {
  return `var(--${section}-tint)`;
}
export function sectionTextColor(section: Section): string {
  return INK_TEXT_SECTIONS.includes(section) ? "var(--ink)" : "#fff";
}

export function SectionChip({
  section,
  icon,
  children,
}: {
  section: Section;
  icon?: ReactNode;
  children: ReactNode;
}) {
  return (
    <span
      className="chip-v2"
      style={
        {
          "--chip": sectionColor(section),
          "--chip-text": sectionTextColor(section),
        } as CSSProperties
      }
    >
      {icon}
      {children}
    </span>
  );
}

export function Card({
  section,
  chip,
  chipIcon,
  headerRight,
  className = "",
  style,
  tinted = false,
  onClick,
  children,
}: {
  section?: Section;
  chip?: ReactNode;
  chipIcon?: ReactNode;
  headerRight?: ReactNode;
  className?: string;
  style?: CSSProperties;
  /** Wash the card background in the section tint */
  tinted?: boolean;
  onClick?: () => void;
  children: ReactNode;
}) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      onClick={onClick}
      className={`card-v2 flex flex-col text-left ${onClick ? "pressable cursor-pointer" : ""} ${className}`}
      style={{
        padding: 16,
        background: tinted && section ? sectionTint(section) : "var(--surface)",
        ...style,
      }}
    >
      {(chip || headerRight) && (
        <div className="flex items-center justify-between shrink-0 mb-3">
          {chip && section ? (
            <SectionChip section={section} icon={chipIcon}>
              {chip}
            </SectionChip>
          ) : (
            <span />
          )}
          {headerRight}
        </div>
      )}
      {children}
    </Tag>
  );
}
