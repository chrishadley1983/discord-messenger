"use client";

import { useState, useRef, useEffect } from "react";

interface AddMoneyPopupProps {
  child: "emmie" | "max";
  onConfirm: (amount: number, category: string, description: string) => void;
  onClose: () => void;
}

const CHILD_CONFIG = {
  emmie: { name: "Emmie", color: "#8B5CF6" },
  max: { name: "Max", color: "#3B82F6" },
};

const CATEGORIES = [
  { key: "gift", emoji: "\u{1F381}", label: "Gift" },
  { key: "chores", emoji: "\u{1F9F9}", label: "Chores" },
  { key: "spent", emoji: "\u{1F6D2}", label: "Spent" },
  { key: "pocket_money", emoji: "\u2B50", label: "Pocket Money" },
  { key: "bonus", emoji: "\u{1F4DA}", label: "Bonus" },
  { key: "penalty", emoji: "\u274C", label: "Penalty" },
];

const QUICK_AMOUNTS = [100, 200, 300, 500, 1000]; // pence

function formatPence(pence: number): string {
  return `\u00a3${(pence / 100).toFixed(pence % 100 === 0 ? 0 : 2)}`;
}

export default function AddMoneyPopup({ child, onConfirm, onClose }: AddMoneyPopupProps) {
  const config = CHILD_CONFIG[child];
  const [category, setCategory] = useState("pocket_money");
  const [amount, setAmount] = useState(300);
  const [isDebit, setIsDebit] = useState(false);
  const [description, setDescription] = useState("");
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, [onClose]);

  // Default to debit for spent/penalty
  useEffect(() => {
    if (category === "spent" || category === "penalty") {
      setIsDebit(true);
    } else {
      setIsDebit(false);
    }
  }, [category]);

  const handleConfirm = () => {
    const finalAmount = isDebit ? -Math.abs(amount) : Math.abs(amount);
    onConfirm(finalAmount, category, description);
  };

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(26,23,16,0.5)" }}
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className="bg-white rounded-3xl shadow-2xl w-[480px] max-w-[95vw] p-6" style={{ animation: "fadeIn 0.2s ease" }}>
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-bold" style={{ color: config.color }}>
            {config.name} &mdash; Add / Remove
          </h2>
          <button onClick={onClose} className="text-2xl text-text-dim cursor-pointer p-1" style={{ minWidth: "44px", minHeight: "44px" }}>
            &times;
          </button>
        </div>

        {/* Category grid */}
        <div className="grid grid-cols-3 gap-2 mb-5">
          {CATEGORIES.map((cat) => (
            <button
              key={cat.key}
              onClick={() => setCategory(cat.key)}
              className="flex flex-col items-center gap-1 py-3 rounded-xl cursor-pointer border-2 transition-all"
              style={{
                borderColor: category === cat.key ? config.color : "#e5e2d9",
                background: category === cat.key ? `${config.color}10` : "white",
                minHeight: "44px",
              }}
            >
              <span className="text-xl">{cat.emoji}</span>
              <span className="text-xs font-medium">{cat.label}</span>
            </button>
          ))}
        </div>

        {/* Credit / Debit toggle */}
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setIsDebit(false)}
            className="flex-1 py-2.5 rounded-xl font-semibold text-sm cursor-pointer border-2 transition-colors"
            style={{
              background: !isDebit ? "#dcfce7" : "white",
              borderColor: !isDebit ? "#16a34a" : "#e5e2d9",
              color: !isDebit ? "#166534" : "#7a7060",
              minHeight: "44px",
            }}
          >
            + Add
          </button>
          <button
            onClick={() => setIsDebit(true)}
            className="flex-1 py-2.5 rounded-xl font-semibold text-sm cursor-pointer border-2 transition-colors"
            style={{
              background: isDebit ? "#fee2e2" : "white",
              borderColor: isDebit ? "#dc2626" : "#e5e2d9",
              color: isDebit ? "#dc2626" : "#7a7060",
              minHeight: "44px",
            }}
          >
            &minus; Remove
          </button>
        </div>

        {/* Quick amount pills */}
        <div className="flex gap-2 mb-4 flex-wrap">
          {QUICK_AMOUNTS.map((a) => (
            <button
              key={a}
              onClick={() => setAmount(a)}
              className="px-4 py-2.5 rounded-xl font-semibold text-sm cursor-pointer border-2 transition-colors"
              style={{
                borderColor: amount === a ? config.color : "#e5e2d9",
                background: amount === a ? `${config.color}10` : "white",
                color: amount === a ? config.color : "#1a1710",
                minHeight: "44px",
              }}
            >
              {formatPence(a)}
            </button>
          ))}
        </div>

        {/* Description */}
        <input
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Description (optional)"
          className="w-full px-4 py-3 rounded-xl border-2 text-sm mb-5 outline-none"
          style={{ borderColor: "#e5e2d9", minHeight: "44px" }}
        />

        {/* Confirm */}
        <button
          onClick={handleConfirm}
          className="w-full py-3.5 rounded-xl font-bold text-base text-white cursor-pointer transition-colors"
          style={{ background: config.color, minHeight: "48px" }}
        >
          {isDebit ? "Remove" : "Add"} {formatPence(amount)} {isDebit ? "from" : "to"} {config.name}
        </button>
      </div>
    </div>
  );
}
