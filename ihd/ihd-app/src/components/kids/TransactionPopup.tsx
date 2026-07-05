"use client";

import Modal from "../ui/Modal";

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
  emmie: { name: "Emmie", color: "var(--emmie)" },
  max: { name: "Max", color: "var(--max)" },
};

const CATEGORY_EMOJI: Record<string, string> = {
  gift: "\u{1F381}",
  chores: "\u{1F9F9}",
  spent: "\u{1F6D2}",
  pocket_money: "⭐",
  bonus: "\u{1F31F}",
  penalty: "❌",
};

function formatPence(pence: number): string {
  const pounds = Math.abs(pence) / 100;
  const sign = pence < 0 ? "-" : "+";
  return `${sign}£${pounds.toFixed(2)}`;
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
  const grouped = groupByDate(transactions);
  const dateKeys = Object.keys(grouped).sort((a, b) => b.localeCompare(a));

  return (
    <Modal onClose={onClose} accent={config.color} title={`${config.name} — Transaction History`}>
      <div className="px-5 pb-5 pt-2">
        {dateKeys.length === 0 ? (
          <div className="text-center text-base py-8" style={{ color: "var(--ink-60)" }}>No transactions yet</div>
        ) : (
          dateKeys.map((dateKey) => (
            <div key={dateKey} className="mb-4 last:mb-0">
              <div className="text-sm font-bold uppercase tracking-widest mb-2" style={{ color: "var(--ink-60)" }}>
                {formatDate(dateKey)}
              </div>
              <div className="flex flex-col gap-2">
                {grouped[dateKey].map((tx) => (
                  <div
                    key={tx.id}
                    className="flex items-center gap-3 px-4 rounded-2xl"
                    style={{ minHeight: 64, background: "var(--surface-alt)", border: "2px solid var(--ink)" }}
                  >
                    <span className="text-2xl">{CATEGORY_EMOJI[tx.category] || "⭐"}</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-base font-semibold truncate">{tx.description || tx.category}</div>
                      {tx.source === "peter" && (
                        <div className="text-sm" style={{ color: "var(--ink-60)" }}>via Peter</div>
                      )}
                    </div>
                    <span
                      className="font-bold text-base"
                      style={{ color: tx.amount >= 0 ? "#16a34a" : "#dc2626" }}
                    >
                      {formatPence(tx.amount)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </Modal>
  );
}
