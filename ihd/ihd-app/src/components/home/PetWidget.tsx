"use client";

import { useState, useEffect, useCallback, useMemo } from "react";

const SLEEP_START = 20;
const SLEEP_END = 7;
const DECAY_BASE = { hunger: 5, happiness: 3, cleanliness: 2 };

const SPECIES_COLORS: Record<string, string> = {
  dragon: "#e74c3c",
  cat: "#f39c12",
  fox: "#e67e22",
  blob: "#9b59b6",
  robot: "#3498db",
};

interface PetData {
  id: string;
  name: string;
  species: string;
  stage: string;
  hunger: number;
  happiness: number;
  cleanliness: number;
  lastUpdated: string;
  poopCount?: number;
  [key: string]: unknown;
}

function isSleeping(): boolean {
  const h = new Date().getHours();
  return h >= SLEEP_START || h < SLEEP_END;
}

function applyDecay(pet: PetData): PetData {
  const now = Date.now();
  const last = new Date(pet.lastUpdated).getTime();
  const hours = (now - last) / 3600000;
  if (hours < 0.01) return pet;
  return {
    ...pet,
    hunger: Math.max(0, Math.min(100, pet.hunger - DECAY_BASE.hunger * hours)),
    happiness: Math.max(
      0,
      Math.min(100, pet.happiness - DECAY_BASE.happiness * hours)
    ),
    cleanliness: Math.max(
      0,
      Math.min(100, pet.cleanliness - DECAY_BASE.cleanliness * hours)
    ),
  };
}

function getMood(pet: PetData, sleeping: boolean): string {
  if (sleeping) return "sleeping";
  const avg = (pet.hunger + pet.happiness + pet.cleanliness) / 3;
  if (avg > 70) return "happy";
  if (avg > 40) return "idle";
  return "sad";
}

function getMoodFace(
  hunger: number,
  happiness: number,
  cleanliness: number
): { face: string; label: string } {
  const avg = (hunger + happiness + cleanliness) / 3;
  if (avg > 75) return { face: "😊", label: "Thriving!" };
  if (avg > 50) return { face: "🙂", label: "Content" };
  if (avg > 30) return { face: "😐", label: "Meh..." };
  if (avg > 15) return { face: "😟", label: "Sad" };
  return { face: "😢", label: "Miserable!" };
}

function statColor(val: number): string {
  if (val > 60) return "#22c55e";
  if (val > 30) return "#f59e0b";
  return "#ef4444";
}

function MiniSprite({
  species,
  stage,
  mood,
  size = 52,
}: {
  species: string;
  stage: string;
  mood: string;
  size?: number;
}) {
  const color = SPECIES_COLORS[species] || "#9b59b6";

  if (stage === "egg") {
    return (
      <svg viewBox="0 0 64 64" width={size} height={size}>
        <ellipse cx="32" cy="36" rx="16" ry="20" fill={color} />
        <ellipse cx="32" cy="36" rx="16" ry="20" fill="white" opacity={0.15} />
      </svg>
    );
  }

  const cx = 32,
    headY = 24;
  const headR = 12;
  const bodyMid = 38;
  const eyeY = headY - 1;
  const gap = species === "robot" ? 6 : 7;

  let eyes = null;
  if (mood === "sleeping") {
    eyes = (
      <>
        <line x1={cx - gap - 3} y1={eyeY} x2={cx - gap + 3} y2={eyeY} stroke="#1a1a2e" strokeWidth={2} strokeLinecap="round" />
        <line x1={cx + gap - 3} y1={eyeY} x2={cx + gap + 3} y2={eyeY} stroke="#1a1a2e" strokeWidth={2} strokeLinecap="round" />
      </>
    );
  } else if (mood === "happy") {
    eyes = (
      <>
        <circle cx={cx - gap} cy={eyeY} r={3} fill="#1a1a2e" />
        <circle cx={cx + gap} cy={eyeY} r={3} fill="#1a1a2e" />
        <circle cx={cx - gap + 1} cy={eyeY - 1} r={1.2} fill="white" />
        <circle cx={cx + gap + 1} cy={eyeY - 1} r={1.2} fill="white" />
      </>
    );
  } else {
    eyes = (
      <>
        <circle cx={cx - gap} cy={eyeY} r={2.5} fill="#1a1a2e" />
        <circle cx={cx + gap} cy={eyeY} r={2.5} fill="#1a1a2e" />
      </>
    );
  }

  let mouth = null;
  if (mood === "happy") {
    mouth = <ellipse cx={cx} cy={headY + 7} rx={3} ry={2.5} fill="#1a1a2e" />;
  } else if (mood === "sad") {
    mouth = (
      <path
        d={`M${cx - 4},${headY + 8} Q${cx},${headY + 5} ${cx + 4},${headY + 8}`}
        fill="none" stroke="#1a1a2e" strokeWidth={1.5} strokeLinecap="round"
      />
    );
  } else if (mood !== "sleeping") {
    mouth = (
      <path
        d={`M${cx - 3},${headY + 6} Q${cx},${headY + 9} ${cx + 3},${headY + 6}`}
        fill="none" stroke="#1a1a2e" strokeWidth={1.5} strokeLinecap="round"
      />
    );
  }

  let body = null;
  switch (species) {
    case "blob":
      body = (
        <g>
          <ellipse cx={cx} cy={bodyMid - 4} rx={20} ry={18} fill={color} />
          <ellipse cx={cx} cy={bodyMid + 4} rx={12} ry={8} fill="white" opacity={0.3} />
          <ellipse cx={cx - 22} cy={bodyMid - 4} rx={3.5} ry={5} fill={color} />
          <ellipse cx={cx + 22} cy={bodyMid - 4} rx={3.5} ry={5} fill={color} />
        </g>
      );
      break;
    case "cat":
      body = (
        <g>
          <ellipse cx={cx} cy={bodyMid} rx={13} ry={14} fill={color} />
          <circle cx={cx} cy={headY} r={headR} fill={color} />
          <polygon points={`${cx - 14},${headY - headR + 4} ${cx - 9},${headY - headR - 9} ${cx - 4},${headY - headR + 4}`} fill={color} />
          <polygon points={`${cx + 14},${headY - headR + 4} ${cx + 9},${headY - headR - 9} ${cx + 4},${headY - headR + 4}`} fill={color} />
          <ellipse cx={cx} cy={headY + 3} rx={2} ry={1.5} fill="#ff9eb5" />
          <path d={`M${cx + 12},${bodyMid + 2} Q${cx + 20},${bodyMid - 8} ${cx + 18},${bodyMid - 14}`} fill="none" stroke={color} strokeWidth={3.5} strokeLinecap="round" />
        </g>
      );
      break;
    case "fox":
      body = (
        <g>
          <ellipse cx={cx} cy={bodyMid} rx={13} ry={14} fill={color} />
          <ellipse cx={cx} cy={bodyMid + 3} rx={7} ry={7} fill="white" opacity={0.6} />
          <circle cx={cx} cy={headY} r={headR} fill={color} />
          <ellipse cx={cx} cy={headY + 4} rx={6} ry={5} fill="white" opacity={0.5} />
          <polygon points={`${cx - 16},${headY - headR + 4} ${cx - 10},${headY - headR - 11} ${cx - 4},${headY - headR + 4}`} fill={color} />
          <polygon points={`${cx + 16},${headY - headR + 4} ${cx + 10},${headY - headR - 11} ${cx + 4},${headY - headR + 4}`} fill={color} />
          <polygon points={`${cx},${headY + 5} ${cx - 2},${headY + 2} ${cx + 2},${headY + 2}`} fill="#1a1a2e" />
          <path d={`M${cx + 13},${bodyMid + 2} Q${cx + 22},${bodyMid - 6} ${cx + 18},${bodyMid - 16}`} fill={color} stroke={color} strokeWidth={5} strokeLinecap="round" />
        </g>
      );
      break;
    case "dragon":
      body = (
        <g>
          <ellipse cx={cx} cy={bodyMid} rx={13} ry={14} fill={color} />
          <ellipse cx={cx} cy={bodyMid} rx={6} ry={5} fill="white" opacity={0.3} />
          <circle cx={cx} cy={headY} r={headR} fill={color} />
          <polygon points={`${cx - 7},${headY - headR + 2} ${cx - 5},${headY - headR - 9} ${cx - 3},${headY - headR + 2}`} fill={color} opacity={0.8} />
          <polygon points={`${cx + 7},${headY - headR + 2} ${cx + 5},${headY - headR - 9} ${cx + 3},${headY - headR + 2}`} fill={color} opacity={0.8} />
          <ellipse cx={cx - 18} cy={bodyMid - 6} rx={3} ry={6} fill={color} opacity={0.5} />
          <ellipse cx={cx + 18} cy={bodyMid - 6} rx={3} ry={6} fill={color} opacity={0.5} />
          <path d={`M${cx},${bodyMid + 12} Q${cx + 10},${bodyMid + 16} ${cx + 16},${bodyMid + 12}`} fill="none" stroke={color} strokeWidth={3} strokeLinecap="round" />
        </g>
      );
      break;
    case "robot":
      body = (
        <g>
          <rect x={cx - 13} y={bodyMid - 10} width={26} height={22} rx={3} fill={color} />
          <rect x={cx - headR} y={headY - headR} width={headR * 2} height={headR * 1.7} rx={3} fill={color} />
          <rect x={cx - headR + 3} y={headY - headR + 3} width={(headR - 3) * 2} height={headR * 1.1} rx={2} fill="#1a1a2e" opacity={0.7} />
          <line x1={cx.toString()} y1={(headY - headR).toString()} x2={cx.toString()} y2={(headY - headR - 8).toString()} stroke="#888" strokeWidth={2} />
          <circle cx={cx} cy={headY - headR - 8} r={2.5} fill="#ff6b6b" />
          <circle cx={cx} cy={bodyMid} r={2.5} fill="#22c55e" opacity={0.7} />
        </g>
      );
      break;
  }

  const animStyle =
    mood === "sleeping"
      ? { animation: "pet-sleep-breathe 4s ease-in-out infinite", transformOrigin: "center bottom" }
      : mood === "happy"
      ? { animation: "pet-happy-bounce 1.2s ease-in-out infinite" }
      : { animation: "pet-breathe 3s ease-in-out infinite", transformOrigin: "center bottom" };

  return (
    <svg viewBox="0 0 64 64" width={size} height={size}>
      <g style={animStyle}>
        {body}
        {eyes}
        {mouth}
      </g>
      {mood === "sleeping" && (
        <>
          <text x={cx + 16} y={eyeY - 6} fontSize={9} fontWeight={800} fill="#6366f1" style={{ animation: "sparkle 2s ease-in-out infinite" }}>Z</text>
          <text x={cx + 21} y={eyeY - 13} fontSize={7} fontWeight={800} fill="#6366f1" style={{ animation: "sparkle 2s ease-in-out infinite", animationDelay: "0.5s" }}>z</text>
        </>
      )}
    </svg>
  );
}

function PetMiniCard({
  pet,
  sleeping,
}: {
  pet: PetData;
  sleeping: boolean;
}) {
  const decayed = useMemo(() => applyDecay(pet), [pet]);
  const mood = getMood(decayed, sleeping);
  const moodInfo = getMoodFace(
    decayed.hunger,
    decayed.happiness,
    decayed.cleanliness
  );

  return (
    <div className="flex items-center gap-3">
      <MiniSprite species={pet.species} stage={pet.stage} mood={mood} size={48} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <p className="text-sm font-bold text-text truncate">{pet.name}</p>
          <span className="text-xs">{moodInfo.face}</span>
        </div>
        <div className="flex gap-1 mt-1">
          {[
            { emoji: "🍕", val: decayed.hunger },
            { emoji: "💜", val: decayed.happiness },
            { emoji: "✨", val: decayed.cleanliness },
          ].map(({ emoji, val }) => (
            <div key={emoji} className="flex items-center gap-0.5 flex-1">
              <span className="text-[10px]">{emoji}</span>
              <div className="flex-1 h-1.5 bg-surface-alt rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${val}%`,
                    backgroundColor: statColor(val),
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function PetWidget() {
  const [pets, setPets] = useState<{
    max: PetData | null;
    emmie: PetData | null;
  }>({ max: null, emmie: null });
  const [sleeping, setSleeping] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showPlayground, setShowPlayground] = useState(false);

  const loadPets = useCallback(async () => {
    try {
      const res = await fetch("/api/pets");
      if (res.ok) {
        const data = await res.json();
        setPets(data.pets || { max: null, emmie: null });
        setSleeping(data.sleeping ?? isSleeping());
      }
    } catch {
      // keep last state
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPets();
    const interval = setInterval(loadPets, 30000);
    return () => clearInterval(interval);
  }, [loadPets]);

  useEffect(() => {
    if (!showPlayground) loadPets();
  }, [showPlayground, loadPets]);

  const hasPets = pets.max || pets.emmie;

  return (
    <>
      <div
        onClick={() => setShowPlayground(true)}
        className="bg-surface border border-border rounded-2xl p-4 shadow-sm cursor-pointer hover:border-accent/30 transition-all active:scale-[0.98]"
      >
        <div className="flex items-center justify-between mb-2">
          <div className="text-xs font-bold uppercase tracking-widest text-text-mid">
            Pets
          </div>
          {sleeping && (
            <span className="text-xs text-text-dim">💤 Sleeping</span>
          )}
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-4">
            <span className="text-2xl">🥚</span>
          </div>
        ) : !hasPets ? (
          <div className="text-center py-3">
            <span className="text-3xl">🥚</span>
            <p className="text-xs text-text-dim mt-1">Tap to hatch a pet!</p>
          </div>
        ) : (
          <div className="space-y-2.5">
            {pets.max && <PetMiniCard pet={pets.max} sleeping={sleeping} />}
            {pets.emmie && (
              <PetMiniCard pet={pets.emmie} sleeping={sleeping} />
            )}
          </div>
        )}
      </div>

      {showPlayground && (
        <div
          className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowPlayground(false);
          }}
        >
          <button
            onClick={() => setShowPlayground(false)}
            className="absolute top-4 right-4 z-[60] w-12 h-12 rounded-full bg-surface shadow-lg hover:bg-surface-alt flex items-center justify-center text-text text-xl font-bold transition-all active:scale-90"
          >
            ✕
          </button>
          <div className="bg-white rounded-2xl overflow-hidden shadow-2xl" style={{ width: "70vw", height: "85vh" }}>
            <iframe
              src="/pets-standalone.html"
              className="w-full h-full border-0"
              title="Pet Playground"
              allow="autoplay"
            />
          </div>
        </div>
      )}
    </>
  );
}
