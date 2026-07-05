"use client";

import { Card } from "../ui/Card";
import Icon from "../ui/Icon";

interface Transaction {
  id: string;
  amount: number;
  category: string;
  description: string;
  date: string;
  source: string;
}

interface BalanceCardProps {
  child: "emmie" | "max";
  balance: number;
  transactions: Transaction[];
  onAddMoney: () => void;
  onViewHistory: () => void;
  onViewGrid: () => void;
}

const CHILD_CONFIG = {
  emmie: { name: "Emmie", emoji: "\u{1F984}", color: "var(--emmie)" },
  max: { name: "Max", emoji: "\u{1F988}", color: "var(--max)" },
};

function formatPence(pence: number): string {
  const pounds = Math.abs(pence) / 100;
  return `£${pounds.toFixed(2)}`;
}

export default function BalanceCard({ child, balance, onAddMoney, onViewHistory, onViewGrid }: BalanceCardProps) {
  const config = CHILD_CONFIG[child];

  return (
    <Card className="h-full min-h-0 flex flex-col" style={{ padding: 0, overflow: "hidden" }}>
      {/* Child-colour header band */}
      <div
        className="flex items-center gap-3 px-5 py-3 shrink-0"
        style={{ background: config.color, borderBottom: "2px solid var(--ink)" }}
      >
        <span className="text-3xl" style={{ display: "inline-block", transform: "rotate(-1.5deg)" }}>
          {config.emoji}
        </span>
        <span
          style={{
            fontFamily: "var(--font-display), sans-serif",
            fontWeight: 800,
            fontSize: 24,
            color: "#fff",
          }}
        >
          {config.name}
        </span>
      </div>

      <div className="flex-1 min-h-0 flex flex-col px-4 py-3">
        {/* Big balance */}
        <div className="flex-1 flex items-center justify-center">
          <span
            style={{
              fontFamily: "var(--font-display), sans-serif",
              fontWeight: 800,
              fontSize: 44,
              color: config.color,
              fontVariantNumeric: "tabular-nums",
              animation: "coinBounce 0.4s ease",
            }}
          >
            {formatPence(balance)}
          </span>
        </div>

        {/* Weekly Grid button */}
        <button
          onClick={onViewGrid}
          className="pressable mb-2 w-full rounded-2xl font-bold cursor-pointer flex items-center justify-center gap-2 shrink-0"
          style={{
            height: 56,
            fontSize: 16,
            border: "2px solid var(--ink)",
            color: config.color,
            background: "var(--surface)",
            boxShadow: "3px 3px 0 var(--ink-08)",
          }}
        >
          <Icon name="clipboard" size={18} /> Weekly Grid
        </button>

        {/* Action buttons */}
        <div className="flex gap-3 shrink-0">
          <button
            onClick={onAddMoney}
            className="pressable flex-1 rounded-2xl font-bold cursor-pointer"
            style={{
              height: 56,
              fontSize: 16,
              background: config.color,
              color: "white",
              border: "2px solid var(--ink)",
              boxShadow: "3px 3px 0 var(--ink-08)",
            }}
          >
            + Add / Remove
          </button>
          <button
            onClick={onViewHistory}
            className="pressable flex-1 rounded-2xl font-bold cursor-pointer flex items-center justify-center gap-2"
            style={{
              height: 56,
              fontSize: 16,
              border: "2px solid var(--ink)",
              color: config.color,
              background: "var(--surface)",
              boxShadow: "3px 3px 0 var(--ink-08)",
            }}
          >
            <Icon name="history" size={18} /> History
          </button>
        </div>
      </div>
    </Card>
  );
}
