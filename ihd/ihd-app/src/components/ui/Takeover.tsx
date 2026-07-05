"use client";

/**
 * Full-screen takeover for rich/immersive content (DESIGN_SPEC_V2 §6):
 * pets playground, practice iframes, trip browser, sensor charts,
 * recipe detail, pocket-money grid.
 *
 * Edge-safety contract:
 * - fixed inset-0 z-300, opaque paper background
 * - fixed 72px header with a 72x72 back button that NEVER scrolls away
 * - body fills the rest; iframes/games live INSIDE the body
 */

import { useEffect, useId, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useModalManager } from "./ModalManager";

interface TakeoverProps {
  onClose: () => void;
  /** Section colour, e.g. "var(--kids)" */
  accent?: string;
  /** Text on the accent: "#fff" (default) or "var(--ink)" for marigold/mint */
  accentText?: string;
  title: ReactNode;
  /** Optional extra header actions (right side) */
  actions?: ReactNode;
  children: ReactNode;
}

export default function Takeover({
  onClose,
  accent = "var(--ink)",
  accentText = "#fff",
  title,
  actions,
  children,
}: TakeoverProps) {
  const id = useId();
  const { register } = useModalManager();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);
  useEffect(() => register(id, onClose), [id, onClose, register]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, [onClose]);

  // Portal to <body>: position:fixed is otherwise trapped by any transformed
  // ancestor (e.g. a stagger-animated card) — E2E finding.
  if (!mounted) return null;
  return createPortal(
    <div
      className="fixed inset-0 flex flex-col"
      style={{
        zIndex: 300,
        background: "var(--paper)",
        animation: "overlayIn 200ms ease both",
      }}
    >
      {/* Fixed header — back button always reachable */}
      <div
        className="flex items-center gap-4 shrink-0 px-3"
        style={{ height: 84, background: accent, borderBottom: "2px solid var(--ink)" }}
      >
        <button
          onClick={onClose}
          aria-label="Back"
          className="pressable flex items-center justify-center gap-1 shrink-0"
          style={{
            width: 72,
            height: 72,
            borderRadius: 16,
            border: "2px solid var(--ink)",
            background: "var(--surface)",
            fontSize: 22,
            fontWeight: 800,
            cursor: "pointer",
            fontFamily: "var(--font-display), sans-serif",
          }}
        >
          ◀
        </button>
        <div
          className="flex-1 min-w-0 truncate"
          style={{
            fontFamily: "var(--font-display), sans-serif",
            fontWeight: 800,
            fontSize: 26,
            color: accentText,
          }}
        >
          {title}
        </div>
        {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
      </div>
      {/* Body */}
      <div className="flex-1 min-h-0 relative">{children}</div>
    </div>,
    document.body
  );
}
