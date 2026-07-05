"use client";

/**
 * Chunky pill nav (DESIGN_SPEC_V2 §5). Active pill = solid section colour +
 * ink border + offset shadow. Whole pill is the touch target (≥64px tall).
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { CSSProperties } from "react";

const NAV_ITEMS: {
  href: string;
  icon: string;
  label: string;
  color: string;
  inkText?: boolean;
}[] = [
  { href: "/", icon: "🏠", label: "Home", color: "var(--home)", inkText: true },
  { href: "/calendar", icon: "📅", label: "Calendar", color: "var(--calendar)" },
  { href: "/meals", icon: "🍽", label: "Meals", color: "var(--meals)" },
  { href: "/kids", icon: "🎒", label: "Kids", color: "var(--kids)" },
  { href: "/media", icon: "🎬", label: "Media", color: "var(--media)" },
  { href: "/control", icon: "💡", label: "Control", color: "var(--control)", inkText: true },
  { href: "/chris", icon: "🧱", label: "HB", color: "var(--hb)" },
];

export default function BottomNav() {
  const pathname = usePathname();

  return (
    <div
      className="flex items-center gap-2 px-3 shrink-0"
      style={{
        height: 76,
        background: "var(--surface)",
        borderTop: "2px solid var(--ink)",
        zIndex: 100,
        position: "relative",
      }}
    >
      {NAV_ITEMS.map((item) => {
        const active = pathname === item.href;
        const style: CSSProperties = active
          ? {
              background: item.color,
              color: item.inkText ? "var(--ink)" : "#fff",
              border: "2px solid var(--ink)",
              boxShadow: "3px 3px 0 var(--ink-08)",
            }
          : {
              background: "transparent",
              color: "var(--text-mid)",
              border: "2px solid transparent",
            };
        return (
          <Link
            key={item.href}
            href={item.href}
            className="pressable flex-1 flex flex-col items-center justify-center gap-0.5 no-underline"
            style={{
              height: 64,
              borderRadius: 18,
              fontFamily: "var(--font-display), sans-serif",
              fontWeight: 700,
              fontSize: 14,
              ...style,
            }}
          >
            <span className="text-xl leading-none">{item.icon}</span>
            <span>{item.label}</span>
          </Link>
        );
      })}
    </div>
  );
}
