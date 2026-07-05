"use client";

import { useState, useEffect, useCallback } from "react";
import BalanceCard from "./BalanceCard";
import AddMoneyPopup from "./AddMoneyPopup";
import TransactionPopup from "./TransactionPopup";
import DadJokeCard from "./DadJokeCard";
import HomeworkPopup, { useHomeworkSummary } from "./HomeworkPopup";
import PocketMoneyGrid from "./PocketMoneyGrid";

interface Transaction {
  id: string;
  amount: number;
  category: string;
  description: string;
  date: string;
  source: string;
}

interface PocketMoneyData {
  emmie: { balance: number; transactions: Transaction[] };
  max: { balance: number; transactions: Transaction[] };
}

interface Joke {
  id: string;
  text: string;
  date: string;
}

type HomeworkMode = "all" | "emmie" | "max" | "spellings";

export default function KidsView() {
  const [pocketMoney, setPocketMoney] = useState<PocketMoneyData | null>(null);
  const [jokes, setJokes] = useState<Joke[]>([]);
  const [addMoneyChild, setAddMoneyChild] = useState<"emmie" | "max" | null>(null);
  const [historyChild, setHistoryChild] = useState<"emmie" | "max" | null>(null);
  const [homeworkMode, setHomeworkMode] = useState<HomeworkMode | null>(null);
  const [gridChild, setGridChild] = useState<"emmie" | "max" | null>(null);
  const hw = useHomeworkSummary();

  const fetchPocketMoney = useCallback(async () => {
    try {
      const res = await fetch("/api/kids/pocket-money");
      if (res.ok) setPocketMoney(await res.json());
    } catch { /* keep last known */ }
  }, []);

  const fetchJokes = useCallback(async () => {
    try {
      const res = await fetch("/api/kids/jokes");
      if (res.ok) {
        const data = await res.json();
        setJokes(data.jokes || []);
      }
    } catch { /* keep last known */ }
  }, []);

  useEffect(() => {
    fetchPocketMoney();
    fetchJokes();
    const t = setInterval(() => { fetchPocketMoney(); fetchJokes(); }, 60 * 1000);
    return () => clearInterval(t);
  }, [fetchPocketMoney, fetchJokes]);

  const handleAddMoney = async (child: "emmie" | "max", amount: number, category: string, description: string) => {
    try {
      const res = await fetch("/api/kids/pocket-money", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ child, amount, category, description, source: "manual" }),
      });
      if (res.ok) {
        await fetchPocketMoney();
      }
    } catch { /* ignore */ }
    setAddMoneyChild(null);
  };

  const emmie = pocketMoney?.emmie || { balance: 0, transactions: [] };
  const max = pocketMoney?.max || { balance: 0, transactions: [] };

  return (
    <div className="h-full flex flex-col min-h-0 p-3 stagger-in">
      {/* Top row: Balance cards (~55% height) */}
      <div className="flex-[55] min-h-0 grid grid-cols-2 gap-4 mb-4">
        <BalanceCard
          child="emmie"
          balance={emmie.balance}
          transactions={emmie.transactions}
          onAddMoney={() => setAddMoneyChild("emmie")}
          onViewHistory={() => setHistoryChild("emmie")}
          onViewGrid={() => setGridChild("emmie")}
        />
        <BalanceCard
          child="max"
          balance={max.balance}
          transactions={max.transactions}
          onAddMoney={() => setAddMoneyChild("max")}
          onViewHistory={() => setHistoryChild("max")}
          onViewGrid={() => setGridChild("max")}
        />
      </div>

      {/* Bottom row: Dad Joke + Homework items (~45% height) */}
      <div className="flex-[45] min-h-0 grid grid-cols-[55fr_45fr] gap-4">
        <DadJokeCard jokes={jokes} />

        {/* Three homework tappable cards */}
        <div className="flex flex-col gap-2">
          <button
            onClick={() => setHomeworkMode("emmie")}
            className="pressable flex-1 rounded-2xl px-4 flex items-center gap-3 cursor-pointer"
            style={{ background: "var(--surface)", border: "2px solid var(--ink)", boxShadow: "3px 3px 0 var(--ink-08)", minHeight: 64 }}
          >
            <span className="text-3xl">{"\u{1F984}"}</span>
            <div className="flex-1 text-left">
              <div className="font-bold" style={{ color: "var(--emmie)", fontSize: 16 }}>Emmie&apos;s Homework</div>
              <div className="text-sm" style={{ color: "var(--ink-60)" }}>
                {hw.emmie.total > 0 ? `${hw.emmie.done}/${hw.emmie.total} done today` : "No tasks today"}
              </div>
            </div>
            <span style={{ color: "var(--ink-30)" }}>{"\u25B8"}</span>
          </button>

          <button
            onClick={() => setHomeworkMode("max")}
            className="pressable flex-1 rounded-2xl px-4 flex items-center gap-3 cursor-pointer"
            style={{ background: "var(--surface)", border: "2px solid var(--ink)", boxShadow: "3px 3px 0 var(--ink-08)", minHeight: 64 }}
          >
            <span className="text-3xl">{"\u{1F988}"}</span>
            <div className="flex-1 text-left">
              <div className="font-bold" style={{ color: "var(--max)", fontSize: 16 }}>Max&apos;s Homework</div>
              <div className="text-sm" style={{ color: "var(--ink-60)" }}>
                {hw.max.total > 0 ? `${hw.max.done}/${hw.max.total} done today` : "No tasks today"}
              </div>
            </div>
            <span style={{ color: "var(--ink-30)" }}>{"\u25B8"}</span>
          </button>

          <button
            onClick={() => setHomeworkMode("spellings")}
            className="pressable flex-1 rounded-2xl px-4 flex items-center gap-3 cursor-pointer"
            style={{ background: "var(--surface)", border: "2px solid var(--ink)", boxShadow: "3px 3px 0 var(--ink-08)", minHeight: 64 }}
          >
            <span className="text-3xl">{"\u{1F4DD}"}</span>
            <div className="flex-1 text-left">
              <div className="font-bold" style={{ color: "#B45309", fontSize: 16 }}>Spellings</div>
              <div className="text-sm" style={{ color: "var(--ink-60)" }}>
                {hw.spellingsDue ? "Tests due" : "Up to date"}
              </div>
            </div>
            <span style={{ color: "var(--ink-30)" }}>{"\u25B8"}</span>
          </button>
        </div>
      </div>

      {/* Popups */}
      {addMoneyChild && (
        <AddMoneyPopup
          child={addMoneyChild}
          onConfirm={(amount, category, description) => handleAddMoney(addMoneyChild, amount, category, description)}
          onClose={() => setAddMoneyChild(null)}
        />
      )}

      {historyChild && (
        <TransactionPopup
          child={historyChild}
          transactions={historyChild === "emmie" ? emmie.transactions : max.transactions}
          onClose={() => setHistoryChild(null)}
        />
      )}

      {homeworkMode && (
        <HomeworkPopup mode={homeworkMode} onClose={() => setHomeworkMode(null)} />
      )}

      {gridChild && (
        <PocketMoneyGrid child={gridChild} onClose={() => setGridChild(null)} />
      )}
    </div>
  );
}
