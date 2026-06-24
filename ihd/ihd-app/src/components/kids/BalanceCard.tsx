"use client";

import { useState } from "react";

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
  emmie: { name: "Emmie", emoji: "\u{1F984}", color: "#8B5CF6", bgTint: "rgba(139,92,246,0.06)", borderTint: "rgba(139,92,246,0.15)" },
  max: { name: "Max", emoji: "\u{1F988}", color: "#3B82F6", bgTint: "rgba(59,130,246,0.06)", borderTint: "rgba(59,130,246,0.15)" },
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
  return `\u00a3${pounds.toFixed(2)}`;
}

export default function BalanceCard({ child, balance, transactions, onAddMoney, onViewHistory, onViewGrid }: BalanceCardProps) {
  const config = CHILD_CONFIG[child];
  const recent = transactions.slice(0, 3);

  return (
    <div
      className="rounded-3xl p-5 shadow-md flex flex-col h-full"
      style={{ background: config.bgTint, border: `2px solid ${config.borderTint}` }}
    >
      {/* Avatar + Name */}
      <div className="flex items-center gap-3 mb-3">
        <div
          className="w-12 h-12 rounded-full flex items-center justify-center text-white font-bold text-lg"
          style={{ background: config.color }}
        >
          {config.name[0]}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-2xl">{config.emoji}</span>
          <span className="text-lg font-semibold" style={{ color: config.color }}>{config.name}</span>
        </div>
      </div>

      {/* Big balance */}
      <div className="flex-1 flex items-center justify-center">
        <span
          className="font-serif font-bold tracking-tight"
          style={{ fontSize: "3.5rem", color: config.color, animation: "coinBounce 0.4s ease" }}
        >
          {formatPence(balance)}
        </span>
      </div>

      {/* Weekly Grid button */}
      <button
        onClick={onViewGrid}
        className="mb-3 w-full py-3 rounded-xl font-semibold text-sm cursor-pointer border-2 transition-all active:scale-[0.98] flex items-center justify-center gap-2"
        style={{ borderColor: `${config.color}40`, color: config.color, background: `${config.color}08`, minHeight: "44px" }}
      >
        {"\u{1F4CB}"} Weekly Grid
      </button>

      {/* Action buttons */}
      <div className="flex gap-3">
        <button
          onClick={onAddMoney}
          className="flex-1 py-3 rounded-xl font-semibold text-sm cursor-pointer transition-colors"
          style={{ background: config.color, color: "white", minHeight: "44px" }}
        >
          + Add / Remove
        </button>
        <button
          onClick={onViewHistory}
          className="flex-1 py-3 rounded-xl font-semibold text-sm cursor-pointer border-2 transition-colors"
          style={{ borderColor: config.color, color: config.color, background: "white", minHeight: "44px" }}
        >
          History
        </button>
      </div>
    </div>
  );
}
