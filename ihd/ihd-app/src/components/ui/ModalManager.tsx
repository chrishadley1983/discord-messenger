"use client";

/**
 * Single-modal rule (DESIGN_SPEC_V2 §6): only one overlay (Modal or Takeover)
 * may be open at a time. Each overlay registers with a unique id on mount;
 * if another is already open, the older one is told to close.
 */

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  type ReactNode,
} from "react";

interface ModalManagerCtx {
  /** Register an opening overlay. Returns an unregister fn. */
  register: (id: string, close: () => void) => () => void;
}

const Ctx = createContext<ModalManagerCtx>({
  register: () => () => {},
});

export function ModalManagerProvider({ children }: { children: ReactNode }) {
  const current = useRef<{ id: string; close: () => void } | null>(null);

  const register = useCallback((id: string, close: () => void) => {
    if (current.current && current.current.id !== id) {
      current.current.close();
    }
    current.current = { id, close };
    return () => {
      if (current.current?.id === id) current.current = null;
    };
  }, []);

  return <Ctx.Provider value={{ register }}>{children}</Ctx.Provider>;
}

export function useModalManager() {
  return useContext(Ctx);
}
