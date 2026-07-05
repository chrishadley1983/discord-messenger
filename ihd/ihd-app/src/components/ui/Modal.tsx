"use client";

/**
 * Centred popup for quick glance/act content (DESIGN_SPEC_V2 §6).
 * - max 720px wide, 85vh tall; content scrolls inside
 * - 56x56 close button, backdrop tap closes, Escape closes
 * - single-modal rule via ModalManager
 */

import { useEffect, useId, useRef, type ReactNode } from "react";
import { useModalManager } from "./ModalManager";

interface ModalProps {
  onClose: () => void;
  /** Section colour for the header chip strip, e.g. "var(--kids)" */
  accent?: string;
  title?: ReactNode;
  children: ReactNode;
  /** Override max width (px). Default 720. */
  maxWidth?: number;
}

export default function Modal({
  onClose,
  accent = "var(--ink)",
  title,
  children,
  maxWidth = 720,
}: ModalProps) {
  const id = useId();
  const backdropRef = useRef<HTMLDivElement>(null);
  const { register } = useModalManager();

  useEffect(() => register(id, onClose), [id, onClose, register]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, [onClose]);

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 flex items-center justify-center"
      style={{
        zIndex: 200,
        background: "rgba(20,16,42,0.55)",
        animation: "backdropIn 150ms ease both",
      }}
      onClick={(e) => {
        if (e.target === backdropRef.current) onClose();
      }}
    >
      <div
        className="card-v2 flex flex-col"
        style={{
          width: `min(${maxWidth}px, calc(100vw - 48px))`,
          maxHeight: "85vh",
          animation: "overlayIn 200ms ease both",
          overflow: "hidden",
        }}
      >
        {/* Header strip */}
        <div
          className="flex items-center justify-between shrink-0 pl-5 pr-3 py-2"
          style={{ borderBottom: "2px solid var(--ink)", background: "var(--surface)" }}
        >
          <div className="flex items-center gap-3 min-w-0">
            <span
              aria-hidden
              style={{
                width: 14,
                height: 14,
                borderRadius: 999,
                background: accent,
                border: "2px solid var(--ink)",
                flexShrink: 0,
              }}
            />
            <div
              className="truncate"
              style={{
                fontFamily: "var(--font-display), sans-serif",
                fontWeight: 700,
                fontSize: 20,
              }}
            >
              {title}
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="pressable flex items-center justify-center shrink-0"
            style={{
              width: 56,
              height: 56,
              borderRadius: 16,
              border: "2px solid var(--ink)",
              background: "var(--surface-alt)",
              fontSize: 24,
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            ✕
          </button>
        </div>
        {/* Body */}
        <div className="flex-1 min-h-0 overflow-y-auto" style={{ paddingBottom: 24 }}>
          {children}
        </div>
      </div>
    </div>
  );
}
