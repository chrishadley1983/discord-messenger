"use client";

import { useState, useEffect, useCallback, useRef } from "react";

const CHILD_COLOURS: Record<string, string> = {
  Emmie: "#7040b8",
  Max: "#2060b8",
};

const ACTIVITY_LABELS: Record<string, string> = {
  paper: "Practice Paper",
  times_tables: "Times Tables",
  tutor_this_week: "Tutor (This Week)",
  tutor_last_week: "Tutor (Last Week)",
  tutor_2w_ago: "Tutor (2 Weeks Ago)",
  tutor_homework: "Tutor Homework",
  tutor_lesson: "Tutor Lesson",
  weak_areas: "Weak Areas",
  revision: "Revision",
  mock_exam: "Mock Exam",
  rest: "Rest",
  tutoring: "Tutoring",
};

interface ScheduleSlot {
  student_id: string;
  day_of_week: number;
  slot_order: number;
  activity_type: string;
  duration_minutes?: number;
}

interface Student { id: string; name: string; year_group?: number; }

interface TutorTopic {
  student_id: string;
  topic: string;
  subject: string;
  notes: string;
  week_start: string;
}

interface Paper {
  topic: string;
  difficulty_level: string;
  surge_url: string;
}

interface Allocation {
  activity_type: string;
  topic?: string;
  difficulty?: string;
  paper_url?: string;
  completed?: boolean;
  duration_minutes?: number;
  slot_order?: number;
}

interface SpellingRow {
  child_name: string;
  year_group: string;
  week_number: number;
  phoneme: string | null;
  words: string | string[];
}

interface TestResult {
  child_name: string;
  week_number: number;
  score: number;
  total: number;
  created_at: string;
}

interface KidsData {
  weekNumber: number;
  spellings: SpellingRow[];
  recentResults: TestResult[];
  practice: {
    todaySchedule: ScheduleSlot[];
    tutorTopics: TutorTopic[];
    papers: Paper[];
    students: Student[];
  };
}

function parseWords(words: string | string[]): string[] {
  if (Array.isArray(words)) return words;
  try { return JSON.parse(words); } catch { return []; }
}

function studentName(students: Student[], id: string): string {
  return students.find((s) => s.id === id)?.name || "Unknown";
}

function getLaunchUrl(slot: ScheduleSlot, students: Student[], tutorTopics: TutorTopic[], papers: Paper[]): { url: string; title: string } | null {
  const s = slot;
  if (s.activity_type === "times_tables") {
    return { url: "https://11plusmate.surge.sh/times-tables.html", title: "Times Tables" };
  }
  if (s.activity_type === "paper" || s.activity_type === "weak_areas" || s.activity_type === "mock_exam") {
    return { url: "https://11plusmate.surge.sh/my-practice.html", title: "Practice Papers" };
  }
  if (s.activity_type.startsWith("tutor_") && s.activity_type !== "tutor_lesson") {
    const weekOffset = s.activity_type === "tutor_this_week" ? 0
      : s.activity_type === "tutor_last_week" ? 1
      : s.activity_type === "tutor_2w_ago" ? 2
      : s.activity_type === "tutor_homework" ? 0 : -1;
    if (weekOffset >= 0) {
      const today = new Date();
      const targetTopic = tutorTopics.find((t) => {
        const topicDate = new Date(t.week_start);
        const weeksAgo = Math.round((today.getTime() - topicDate.getTime()) / (7 * 24 * 60 * 60 * 1000));
        return weeksAgo >= weekOffset && weeksAgo < weekOffset + 1;
      });
      if (targetTopic) {
        const student = students.find((st) => st.id === s.student_id);
        const levelMap: Record<number, string> = { 2: "year4", 3: "year4", 4: "year5", 5: "pretest" };
        const targetLevel = student?.year_group ? levelMap[student.year_group] || "year4" : "year4";
        const matchedPaper = papers.find((p) => p.topic === targetTopic.topic && p.difficulty_level === targetLevel)
          || papers.find((p) => p.topic === targetTopic.topic);
        if (matchedPaper) {
          const label = targetTopic.topic.replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase());
          return { url: matchedPaper.surge_url, title: `${label} (${targetTopic.subject})` };
        }
        return { url: "https://11plusmate.surge.sh/my-practice.html", title: ACTIVITY_LABELS[s.activity_type] || s.activity_type };
      }
    }
    return { url: "https://11plusmate.surge.sh/my-practice.html", title: ACTIVITY_LABELS[s.activity_type] || s.activity_type };
  }
  return null;
}

function IframeModal({ url, title, onClose }: { url: string; title: string; onClose: () => void }) {
  const overlayRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, [onClose]);

  return (
    <div ref={overlayRef} className="fixed inset-0 z-50 flex"
      style={{ background: "rgba(26, 23, 16, 0.5)" }}>
      <div className="bg-bg m-3 rounded-2xl shadow-xl flex flex-col overflow-hidden w-full">
        <div className="flex items-center gap-3 p-3 border-b border-border flex-shrink-0">
          <button onClick={onClose}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium bg-surface-alt border border-border cursor-pointer hover:bg-border transition-colors">
            &lsaquo; Back
          </button>
          <span className="text-sm text-text-mid truncate">{title}</span>
        </div>
        <iframe src={url} className="flex-1 w-full border-none" title={title} allow="autoplay; microphone; speaker; clipboard-write" />
      </div>
    </div>
  );
}

export default function KidsWidget() {
  const [data, setData] = useState<KidsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [iframeUrl, setIframeUrl] = useState<string | null>(null);
  const [iframeTitle, setIframeTitle] = useState("");
  const [sessionCache, setSessionCache] = useState<Record<string, string>>({});
  const [rawSessions, setRawSessions] = useState<Record<string, { session_token: string; student_id: string }>>({});
  const [allocations, setAllocations] = useState<Record<string, Allocation[]>>({});

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch("/api/kids?action=summary");
      if (res.ok) {
        const d = await res.json();
        if (!d.error) setData(d);
      }
    } catch {
      // keep last known
    } finally {
      setLoading(false);
    }
  }, []);

  // Pre-fetch child sessions for iframe auth (avoids cross-origin localStorage issues)
  const fetchChildSessions = useCallback(async () => {
    const sessions: Record<string, { session_token: string; student_id: string }> = {};
    for (const name of ["Emmie", "Max"]) {
      try {
        const res = await fetch("/api/kids", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "get_child_session", child_name: name }),
        });
        const session = await res.json();
        if (session?.session_token) {
          const ps = btoa(JSON.stringify(session));
          setSessionCache((prev) => ({ ...prev, [name]: ps }));
          sessions[name] = { session_token: session.session_token, student_id: session.student_id };
        }
      } catch { /* ignore */ }
    }
    setRawSessions(sessions);
    return sessions;
  }, []);

  // Fetch today's paper allocations for each child
  const fetchAllocations = useCallback(async (sessions: Record<string, { session_token: string; student_id: string }>) => {
    for (const [name, sess] of Object.entries(sessions)) {
      try {
        const res = await fetch("/api/kids", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "get_allocations",
            session_token: sess.session_token,
            student_id: sess.student_id,
          }),
        });
        const data = await res.json();
        if (data?.allocations) {
          setAllocations((prev) => ({ ...prev, [name]: data.allocations }));
        }
      } catch { /* ignore */ }
    }
  }, []);

  useEffect(() => {
    fetchData();
    fetchChildSessions().then((sessions) => {
      if (Object.keys(sessions).length > 0) fetchAllocations(sessions);
    });
    const t = setInterval(fetchData, 10 * 60 * 1000);
    return () => clearInterval(t);
  }, [fetchData, fetchChildSessions, fetchAllocations]);

  // Build iframe URL with session token and IHD flag
  const buildIframeUrl = useCallback((baseUrl: string, childName?: string) => {
    const ps = childName ? sessionCache[childName] : undefined;
    const sep = baseUrl.includes("?") ? "&" : "?";
    const params = [
      ps ? `ps=${encodeURIComponent(ps)}` : "",
      "ihd=1",
      `v=${Date.now()}`,
    ].filter(Boolean).join("&");
    return `${baseUrl}${sep}${params}`;
  }, [sessionCache]);

  if (loading) {
    return (
      <div className="bg-surface border border-border rounded-2xl p-4 shadow-sm flex-1 min-h-0">
        <div className="text-xs font-bold uppercase tracking-widest text-text-mid">
          Kids Learning
        </div>
        <div className="text-sm text-text-dim text-center py-4">Loading...</div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="bg-surface border border-border rounded-2xl p-4 shadow-sm flex-1 min-h-0">
        <div className="text-xs font-bold uppercase tracking-widest text-text-mid">
          Kids Learning
        </div>
        <div className="text-sm text-text-dim text-center py-4">No data</div>
      </div>
    );
  }

  const students = data.practice?.students || [];
  const todaySchedule = data.practice?.todaySchedule || [];
  const tutorTopics = data.practice?.tutorTopics || [];
  const papers = data.practice?.papers || [];

  // Get latest result per child for this week
  const thisWeekResults = data.recentResults.filter(
    (r) => r.week_number === data.weekNumber
  );

  // Group today's schedule by student, filter rest
  const scheduleByStudent: Record<string, ScheduleSlot[]> = {};
  todaySchedule.forEach((slot) => {
    if (slot.activity_type === "rest") return;
    const name = studentName(students, slot.student_id);
    if (!scheduleByStudent[name]) scheduleByStudent[name] = [];
    scheduleByStudent[name].push(slot);
  });

  // Build per-child data combining schedule + spellings
  const childNames = ["Emmie", "Max"];
  const childData = childNames.map((name) => {
    const col = CHILD_COLOURS[name] || "#888";
    const slots = scheduleByStudent[name] || [];
    const spelling = data.spellings.find((s) => s.child_name === name);
    const words = spelling ? parseWords(spelling.words) : [];
    const results = thisWeekResults.filter((r) => r.child_name === name);
    const bestResult = results.length > 0
      ? results.reduce((a, b) => (a.score / a.total > b.score / b.total ? a : b))
      : null;
    return { name, col, slots, spelling, words, bestResult };
  });

  return (
    <>
      <div className="bg-surface border border-border rounded-2xl p-3 shadow-sm flex-1 min-h-0 flex flex-col overflow-hidden">
        <div className="flex items-center justify-between mb-2">
          <div className="text-xs font-bold uppercase tracking-widest text-text-mid">
            Kids Learning
          </div>
          <div className="text-xs text-text-dim">Week {data.weekNumber}</div>
        </div>

        {/* Two-column: one per child */}
        <div className="flex-1 min-h-0 grid grid-cols-2 gap-2">
          {childData.map(({ name, col, slots, spelling, words, bestResult }) => (
            <div key={name} className="flex flex-col gap-1.5 min-h-0">
              {/* Child name header */}
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-bold uppercase" style={{ color: col }}>{name}</span>
              </div>

              {/* Today's practice — show allocated papers if available, fallback to schedule slots */}
              {slots.length > 0 && (() => {
                const childAllocs = allocations[name] || [];
                const hasAllocs = childAllocs.length > 0;
                // Filter to actionable allocations (not rest)
                const activeAllocs = hasAllocs
                  ? childAllocs.filter((a) => a.activity_type !== "rest")
                  : [];

                return (
                  <div className="p-1.5 rounded-lg" style={{ background: "#eff6ff" }}>
                    <div className="text-[10px] font-bold uppercase text-blue-600 tracking-wide mb-0.5">
                      Today&apos;s Practice
                    </div>
                    {hasAllocs && activeAllocs.length > 0 ? (
                      // Show specific allocated papers with topics
                      activeAllocs.map((a, i) => {
                        const topicLabel = a.topic && a.topic !== "TBD"
                          ? a.topic.replace(/-/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase())
                          : null;
                        const label = ACTIVITY_LABELS[a.activity_type] || a.activity_type;
                        const title = topicLabel ? `${label}: ${topicLabel}` : label;
                        const url = a.paper_url || (a.activity_type === "times_tables" ? "https://11plusmate.surge.sh/times-tables.html" : null);
                        const diffLabel = a.difficulty === "actual_test" ? "Kent" : a.difficulty?.replace("_", " ");

                        return (
                          <div key={i}
                            className={`flex items-center gap-1 text-xs leading-tight py-0.5 ${url ? "cursor-pointer hover:bg-blue-100 rounded px-0.5 -mx-0.5" : ""}`}
                            onClick={url ? () => { setIframeUrl(buildIframeUrl(url, name)); setIframeTitle(title); } : undefined}
                          >
                            {a.completed ? (
                              <span className="text-green-600 flex-shrink-0">{"\u2713"}</span>
                            ) : (
                              <span className="text-blue-400 flex-shrink-0">{"\u25CB"}</span>
                            )}
                            <span className={`truncate ${a.completed ? "text-green-700" : "text-text-mid"}`}>
                              {topicLabel || label}
                            </span>
                            {diffLabel && (
                              <span className="text-[9px] font-bold uppercase text-blue-400 flex-shrink-0">{diffLabel}</span>
                            )}
                            {url && <span className="text-text-dim ml-auto flex-shrink-0">&#9656;</span>}
                          </div>
                        );
                      })
                    ) : (
                      // Fallback to generic schedule slots
                      slots.map((s, i) => {
                        const target = getLaunchUrl(s, students, tutorTopics, papers);
                        return (
                          <div key={i}
                            className={`flex items-center gap-1 text-xs leading-tight py-0.5 ${target ? "cursor-pointer hover:bg-blue-100 rounded px-0.5 -mx-0.5" : ""}`}
                            onClick={target ? () => { setIframeUrl(buildIframeUrl(target.url, name)); setIframeTitle(target.title); } : undefined}
                          >
                            <span className="text-text-mid truncate">{ACTIVITY_LABELS[s.activity_type] || s.activity_type}</span>
                            {target && <span className="text-text-dim ml-auto flex-shrink-0">&#9656;</span>}
                          </div>
                        );
                      })
                    )}
                  </div>
                );
              })()}

              {/* Spellings */}
              {spelling && (
                <div className="p-1.5 bg-surface-alt rounded-lg flex flex-col gap-1" style={{ borderLeft: `3px solid ${col}` }}>
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-bold uppercase text-text-mid tracking-wide">Spellings</span>
                    {bestResult ? (
                      <span className="text-xs font-bold" style={{
                        color: bestResult.score / bestResult.total >= 0.8 ? "#166534"
                          : bestResult.score / bestResult.total >= 0.5 ? "#92400e" : "#dc2626",
                      }}>
                        {bestResult.score}/{bestResult.total}
                      </span>
                    ) : (
                      <span className="text-[10px] text-text-dim">Not tested</span>
                    )}
                  </div>
                  {spelling.phoneme && (
                    <span className="text-[10px] text-text-dim -mt-0.5">&ldquo;{spelling.phoneme}&rdquo;</span>
                  )}
                  <div className="grid grid-cols-2 gap-1">
                    {words.map((word, i) => (
                      <span key={i} className="px-1.5 py-0.5 rounded-md text-xs bg-surface border border-border text-center truncate">{word}</span>
                    ))}
                  </div>
                  <button
                    className="w-full py-1 rounded-md text-[11px] font-semibold cursor-pointer border border-accent/30 bg-accent/10 text-accent hover:bg-accent/20 transition-colors mt-0.5"
                    onClick={() => {
                      setIframeUrl(buildIframeUrl("https://hadley-spelling-test.surge.sh/", name));
                      setIframeTitle(`Spelling Test — ${name}`);
                    }}
                  >
                    Spelling Test
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>

        {data.spellings.length === 0 && (
          <div className="text-xs text-text-dim text-center py-2">No spellings this week</div>
        )}
      </div>

      {iframeUrl && (
        <IframeModal url={iframeUrl} title={iframeTitle} onClose={() => setIframeUrl(null)} />
      )}
    </>
  );
}
