"use client";

import { useRef, useEffect } from "react";

interface Transaction {
  id: string;
  amount: number;
  category: string;
  description: string;
  date: string;
  source: string;
}

interface TransactionPopupProps {
  child: "emmie" | "max";
  transactions: Transaction[];
  onClose: () => void;
}

const CHILD_CONFIG = {
  emmie: { name: "Emmie", color: "#8B5CF6" },
  max: { name: "Max", color: "#3B82F6" },
};

const CATEGORY_EMOJI: Record<string, string> = {
  gift: "\u{1F381}",
  chores: "\u{1F9F9}",
  spent: "\u{1F6D2}",
  pocket_money: "\u2B50",
  bonus: "\u{1F31F}",
  penalty: "\u274C",
};

function formatPence(pence: number): string {
  const pounds = Math.abs(pence) / 100;
  const sign = pence < 0 ? "-" : "+";
  return `${sign}\u00a3${pounds.toFixed(2)}`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function groupByDate(txs: Transaction[]): Record<string, Transaction[]> {
  const groups: Record<string, Transaction[]> = {};
  for (const tx of txs) {
    const key = tx.date.slice(0, 10);
    if (!groups[key]) groups[key] = [];
    groups[key].push(tx);
  }
  return groups;
}

export default function TransactionPopup({ child, transactions, onClose }: TransactionPopupProps) {
  const config = CHILD_CONFIG[child];
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, [onClose]);

  const grouped = groupByDate(transactions);
  const dateKeys = Object.keys(grouped).sort((a, b) => b.localeCompare(a));

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(26,23,16,0.5)" }}
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className="bg-white rounded-3xl shadow-2xl w-[500px] max-w-[95vw] max-h-[80vh] flex flex-col" style={{ animation: "fadeIn 0.2s ease" }}>
        <div className="flex items-center justify-between p-5 pb-3 flex-shrink-0">
          <h2 className="text-lg font-bold" style={{ color: config.color }}>
            {config.name} &mdash; Transaction History
          </h2>
          <button onClick={onClose} className="text-2xl text-text-dim cursor-pointer p-1" style={{ minWidth: "44px", minHeight: "44px" }}>
            &times;
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 pb-5">
          {dateKeys.length === 0 ? (
            <div className="text-center text-text-dim py-8">No transactions yet</div>
          ) : (
            dateKeys.map((dateKey) => (
              <div key={dateKey} className="mb-4 last:mb-0">
                <div className="text-xs font-bold uppercase tracking-widest text-text-mid mb-2">
                  {formatDate(dateKey)}
                </div>
                <div className="flex flex-col gap-1.5">
                  {grouped[dateKey].map((tx) => (
                    <div key={tx.id} className="flex items-center gap-3 py-2 px-3 rounded-xl bg-surface-alt/50">
                      <span className="text-lg">{CATEGORY_EMOJI[tx.category] || "\u2B50"}</span>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium truncate">{tx.description || tx.category}</div>
                        {tx.source === "peter" && (
                          <div className="text-xs text-text-dim">via Peter</div>
                        )}
                      </div>
                      <span className={`font-bold text-sm ${tx.amount >= 0 ? "text-green-600" : "text-red-500"}`}>
                        {formatPence(tx.amount)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
