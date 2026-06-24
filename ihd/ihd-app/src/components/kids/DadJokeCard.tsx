"use client";

import { useState } from "react";

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
      <div className="rounded-3xl p-5 shadow-md flex flex-col items-center justify-center h-full"
        style={{ background: "rgba(251,191,36,0.06)", border: "2px solid rgba(251,191,36,0.15)" }}>
        <div className="text-3xl mb-2">{"\u{1F4AC}"}</div>
        <div className="text-sm font-semibold text-text-mid">Peter says...</div>
        <div className="text-xs text-text-dim mt-1">No jokes yet! Peter needs to send one.</div>
      </div>
    );
  }

  const joke = jokes[index];
  const advance = () => setIndex((i) => (i + 1) % count);

  return (
    <div className="rounded-3xl p-5 shadow-md flex flex-col h-full"
      style={{ background: "rgba(251,191,36,0.06)", border: "2px solid rgba(251,191,36,0.15)" }}>

      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-2xl">{"\u{1F4AC}"}</span>
        <span className="text-sm font-semibold text-amber-700">Peter says...</span>
        {count > 1 && (
          <span className="text-xs text-text-dim ml-auto">tap joke to see next</span>
        )}
      </div>

      {/* Tappable speech bubble — tap to cycle */}
      <div
        className="flex-1 flex items-center justify-center px-2 cursor-pointer active:opacity-80 transition-opacity"
        onClick={advance}
      >
        <div
          key={joke.id}
          className="relative bg-white rounded-2xl p-4 shadow-sm w-full"
          style={{ animation: "jokeReveal 0.3s ease", border: "1px solid rgba(251,191,36,0.2)" }}
        >
          <p className="text-base leading-relaxed text-center">{joke.text}</p>
          <div className="absolute -bottom-2 left-8 w-4 h-4 bg-white rotate-45"
            style={{ border: "1px solid rgba(251,191,36,0.2)", borderTop: "none", borderLeft: "none" }} />
        </div>
      </div>

      {/* Dot indicators */}
      {count > 1 && (
        <div className="flex items-center justify-center gap-3 mt-4">
          {jokes.map((j, i) => (
            <span
              key={j.id}
              className="rounded-full block transition-all"
              style={{
                width: i === index ? 24 : 10,
                height: 10,
                background: i === index ? "#f59e0b" : "#d1cdc4",
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
