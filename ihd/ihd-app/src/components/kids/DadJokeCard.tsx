"use client";

import { useState } from "react";
import { Card } from "../ui/Card";

interface Joke {
  id: string;
  text: string;
  date: string;
}

interface DadJokeCardProps {
  jokes: Joke[];
}

export default function DadJokeCard({ jokes }: DadJokeCardProps) {
  const [index, setIndex] = useState(0);
  const count = jokes.length;

  if (count === 0) {
    return (
      <Card section="kids" chip="Peter Says" chipIcon={"\u{1F4AC}"} className="h-full min-h-0">
        <div className="flex-1 min-h-0 flex flex-col items-center justify-center gap-2 text-center">
          <div className="text-4xl">{"\u{1F4AC}"}</div>
          <div className="text-base font-semibold" style={{ color: "var(--ink-60)" }}>No jokes yet!</div>
          <div className="text-sm" style={{ color: "var(--ink-60)" }}>Peter needs to send one.</div>
        </div>
      </Card>
    );
  }

  const joke = jokes[index];
  const advance = () => setIndex((i) => (i + 1) % count);

  return (
    <Card
      section="kids"
      chip="Peter Says"
      chipIcon={"\u{1F4AC}"}
      className="h-full min-h-0"
      headerRight={
        count > 1 ? (
          <span className="text-sm font-semibold" style={{ color: "var(--ink-60)" }}>tap for next</span>
        ) : undefined
      }
    >
      <div
        className="flex-1 min-h-0 flex items-center justify-center px-2 cursor-pointer active:opacity-85 transition-opacity"
        onClick={advance}
      >
        <div
          key={joke.id}
          className="relative w-full rounded-2xl p-5"
          style={{
            animation: "jokeReveal 0.3s ease",
            background: "var(--surface)",
            border: "2px solid var(--ink)",
            boxShadow: "4px 4px 0 var(--kids-tint)",
          }}
        >
          <p
            className="text-center leading-snug"
            style={{ fontFamily: "var(--font-display), sans-serif", fontWeight: 700, fontSize: 20 }}
          >
            {joke.text}
          </p>
          <div
            className="absolute -bottom-2 left-8"
            style={{
              width: 16,
              height: 16,
              background: "var(--surface)",
              border: "2px solid var(--ink)",
              borderTop: "none",
              borderLeft: "none",
              transform: "rotate(45deg)",
            }}
          />
        </div>
      </div>

      {count > 1 && (
        <div className="flex items-center justify-center gap-3 mt-4 shrink-0">
          {jokes.map((j, i) => (
            <span
              key={j.id}
              className="rounded-full block transition-all"
              style={{
                width: i === index ? 28 : 12,
                height: 12,
                background: i === index ? "var(--kids)" : "var(--surface)",
                border: `2px solid ${i === index ? "var(--ink)" : "var(--ink-30)"}`,
              }}
            />
          ))}
        </div>
      )}
    </Card>
  );
}
