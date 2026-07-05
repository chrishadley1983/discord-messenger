"use client";

import { useState, useEffect } from "react";
import Modal from "../ui/Modal";

interface AddMoneyPopupProps {
  child: "emmie" | "max";
  onConfirm: (amount: number, category: string, description: string) => void;
  onClose: () => void;
}

const CHILD_CONFIG = {
  emmie: { name: "Emmie", color: "var(--emmie)" },
  max: { name: "Max", color: "var(--max)" },
};

const CATEGORIES = [
  { key: "gift", emoji: "\u{1F381}", label: "Gift" },
  { key: "chores", emoji: "\u{1F9F9}", label: "Chores" },
  { key: "spent", emoji: "\u{1F6D2}", label: "Spent" },
  { key: "pocket_money", emoji: "⭐", label: "Pocket Money" },
  { key: "bonus", emoji: "\u{1F31F}", label: "Bonus" },
  { key: "penalty", emoji: "❌", label: "Penalty" },
];

const QUICK_AMOUNTS = [100, 200, 300, 500, 1000]; // pence

function formatPence(pence: number): string {
  return `£${(pence / 100).toFixed(pence % 100 === 0 ? 0 : 2)}`;
}

export default function AddMoneyPopup({ child, onConfirm, onClose }: AddMoneyPopupProps) {
  const config = CHILD_CONFIG[child];
  const [category, setCategory] = useState("pocket_money");
  const [amount, setAmount] = useState(300);
  const [isDebit, setIsDebit] = useState(false);
  const [description, setDescription] = useState("");

  // Default to debit for spent/penalty
  useEffect(() => {
    setIsDebit(category === "spent" || category === "penalty");
  }, [category]);

  const handleConfirm = () => {
    const finalAmount = isDebit ? -Math.abs(amount) : Math.abs(amount);
    onConfirm(finalAmount, category, description);
  };

  return (
    <Modal onClose={onClose} accent="var(--kids)" title={`${config.name} — Add / Remove`} maxWidth={560}>
      <div className="p-5">
        {/* Category grid */}
        <div className="grid grid-cols-3 gap-3 mb-4">
          {CATEGORIES.map((cat) => (
            <button
              key={cat.key}
              onClick={() => setCategory(cat.key)}
              className="pressable flex flex-col items-center justify-center gap-1 rounded-2xl cursor-pointer"
              style={{
                height: 72,
                border: `2px solid ${category === cat.key ? config.color : "var(--ink)"}`,
                background: category === cat.key ? `${config.color}18` : "var(--surface)",
                boxShadow: "3px 3px 0 var(--ink-08)",
              }}
            >
              <span className="text-2xl">{cat.emoji}</span>
              <span className="text-sm font-semibold">{cat.label}</span>
            </button>
          ))}
        </div>

        {/* Credit / Debit toggle */}
        <div className="flex gap-3 mb-4">
          <button
            onClick={() => setIsDebit(false)}
            className="pressable flex-1 rounded-2xl font-bold cursor-pointer"
            style={{
              height: 64,
              fontSize: 16,
              background: !isDebit ? "#dcfce7" : "var(--surface)",
              border: `2px solid ${!isDebit ? "#16a34a" : "var(--ink)"}`,
              color: !isDebit ? "#166534" : "var(--ink-60)",
              boxShadow: "3px 3px 0 var(--ink-08)",
            }}
          >
            + Add
          </button>
          <button
            onClick={() => setIsDebit(true)}
            className="pressable flex-1 rounded-2xl font-bold cursor-pointer"
            style={{
              height: 64,
              fontSize: 16,
              background: isDebit ? "#fee2e2" : "var(--surface)",
              border: `2px solid ${isDebit ? "#dc2626" : "var(--ink)"}`,
              color: isDebit ? "#dc2626" : "var(--ink-60)",
              boxShadow: "3px 3px 0 var(--ink-08)",
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
              className="pressable rounded-2xl font-bold cursor-pointer px-5"
              style={{
                height: 64,
                fontSize: 16,
                border: `2px solid ${amount === a ? config.color : "var(--ink)"}`,
                background: amount === a ? `${config.color}18` : "var(--surface)",
                color: amount === a ? config.color : "var(--ink)",
                boxShadow: "3px 3px 0 var(--ink-08)",
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
          className="w-full px-4 rounded-2xl text-base mb-5 outline-none"
          style={{ height: 64, border: "2px solid var(--ink)" }}
        />

        {/* Confirm */}
        <button
          onClick={handleConfirm}
          className="pressable w-full rounded-2xl font-bold text-white cursor-pointer"
          style={{ height: 72, fontSize: 18, background: config.color, border: "2px solid var(--ink)", boxShadow: "4px 4px 0 var(--ink-08)" }}
        >
          {isDebit ? "Remove" : "Add"} {formatPence(amount)} {isDebit ? "from" : "to"} {config.name}
        </button>
      </div>
    </Modal>
  );
}
