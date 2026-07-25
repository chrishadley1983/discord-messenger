"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Card } from "../ui/Card";
import Takeover from "../ui/Takeover";
import Icon from "../ui/Icon";
import EmptyState from "../ui/EmptyState";

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

export default function KidsWidget() {
  const [data, setData] = useState<KidsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [iframeUrl, setIframeUrl] = useState<string | null>(null);
  const [iframeTitle, setIframeTitle] = useState("");
  const [sessionCache, setSessionCache] = useState<Record<string, string>>({});
  const [allocations, setAllocations] = useState<Record<string, Allocation[]>>({});
  const fetchedRef = useRef(false);

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
    if (!fetchedRef.current) {
      fetchedRef.current = true;
      fetchChildSessions().then((sessions) => {
        if (Object.keys(sessions).length > 0) fetchAllocations(sessions);
      });
    }
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
      <Card section="kids" chip="Kids Learning" chipIcon={<Icon name="backpack" size={16} />} className="flex-1 min-h-0">
        <div className="text-base text-ink/60 text-center py-4">Loading...</div>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card section="kids" chip="Kids Learning" chipIcon={<Icon name="backpack" size={16} />} className="flex-1 min-h-0">
        <div className="text-base text-ink/60 text-center py-4">No data</div>
      </Card>
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
      <Card section="kids" chip="Kids Learning" chipIcon={<Icon name="backpack" size={16} />} className="flex-1 min-h-0"
        headerRight={<span className="text-sm text-ink/60 font-semibold">Week {data.weekNumber}</span>}
      >
        {/* Two-column: one per child */}
        <div className="flex-1 min-h-0 grid grid-cols-2 gap-2.5 overflow-hidden">
          {childData.map(({ name, col, slots, spelling, words, bestResult }) => (
            <div key={name} className="flex flex-col gap-1.5 min-h-0 overflow-y-auto overflow-x-hidden">
              {/* Child name header */}
              <div
                className="text-sm font-bold uppercase tracking-wide"
                style={{ fontFamily: "var(--font-display), sans-serif", color: col }}
              >
                {name}
              </div>

              {slots.length === 0 && !spelling && (
                <EmptyState icon="backpack" headline="Nothing set today" compact />
              )}

              {/* Today's practice — show allocated papers if available, fallback to schedule slots */}
              {slots.length > 0 && (() => {
                const childAllocs = allocations[name] || [];
                const hasAllocs = childAllocs.length > 0;
                const activeAllocs = hasAllocs
                  ? childAllocs.filter((a) => a.activity_type !== "rest")
                  : [];

                return (
                  <div className="p-2 rounded-xl flex flex-col gap-1" style={{ background: "var(--kids-tint)" }}>
                    <div className="text-[13px] font-bold uppercase text-kids tracking-wide">
                      Today&apos;s Practice
                    </div>
                    {hasAllocs && activeAllocs.length > 0 ? (
                      activeAllocs.map((a, i) => {
                        const topicLabel = a.topic && a.topic !== "TBD"
                          ? a.topic.replace(/-/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase())
                          : null;
                        const label = ACTIVITY_LABELS[a.activity_type] || a.activity_type;
                        const title = topicLabel ? `${label}: ${topicLabel}` : label;
                        const url = a.paper_url || (a.activity_type === "times_tables" ? "https://11plusmate.surge.sh/times-tables.html" : null);
                        const diffLabel = a.difficulty === "actual_test" ? "Kent" : a.difficulty?.replace("_", " ");

                        return (
                          <button
                            key={i}
                            className={`pressable flex items-center gap-2 text-left rounded-lg px-2 border-none ${url ? "cursor-pointer bg-surface" : "bg-transparent cursor-default"}`}
                            style={{ minHeight: 56 }}
                            onClick={url ? () => { setIframeUrl(buildIframeUrl(url, name)); setIframeTitle(title); } : undefined}
                          >
                            {a.completed ? (
                              <span className="text-good flex-shrink-0 text-lg">{"✓"}</span>
                            ) : (
                              <span className="text-kids flex-shrink-0 text-lg">{"○"}</span>
                            )}
                            <span className="truncate text-base font-medium flex-1">
                              {topicLabel || label}
                            </span>
                            {diffLabel && (
                              <span className="text-[13px] font-bold uppercase text-kids flex-shrink-0">{diffLabel}</span>
                            )}
                            {url && <span className="text-ink/40 flex-shrink-0">&#9656;</span>}
                          </button>
                        );
                      })
                    ) : (
                      slots.map((s, i) => {
                        const target = getLaunchUrl(s, students, tutorTopics, papers);
                        return (
                          <button
                            key={i}
                            className={`pressable flex items-center gap-2 text-left rounded-lg px-2 border-none ${target ? "cursor-pointer bg-surface" : "bg-transparent cursor-default"}`}
                            style={{ minHeight: 56 }}
                            onClick={target ? () => { setIframeUrl(buildIframeUrl(target.url, name)); setIframeTitle(target.title); } : undefined}
                          >
                            <span className="text-base font-medium text-ink truncate flex-1">{ACTIVITY_LABELS[s.activity_type] || s.activity_type}</span>
                            {target && <span className="text-ink/40 flex-shrink-0">&#9656;</span>}
                          </button>
                        );
                      })
                    )}
                  </div>
                );
              })()}

              {/* Spellings */}
              {spelling && (
                <div className="p-2 rounded-xl flex flex-col gap-1.5" style={{ background: "var(--surface-alt)", borderLeft: `3px solid ${col}` }}>
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] font-bold uppercase text-ink/60 tracking-wide">Spellings</span>
                    {bestResult ? (
                      <span className="text-base font-bold" style={{
                        color: bestResult.score / bestResult.total >= 0.8 ? "var(--good)"
                          : bestResult.score / bestResult.total >= 0.5 ? "var(--warn)" : "var(--bad)",
                      }}>
                        {bestResult.score}/{bestResult.total}
                      </span>
                    ) : (
                      <span className="text-[13px] text-ink/40">Not tested</span>
                    )}
                  </div>
                  {spelling.phoneme && (
                    <span className="text-[13px] text-ink/60">&ldquo;{spelling.phoneme}&rdquo;</span>
                  )}
                  <div className="grid grid-cols-2 gap-1">
                    {words.map((word, i) => (
                      <span key={i} className="px-1.5 py-1 rounded-md text-sm bg-surface border-2 border-ink/10 text-center truncate">{word}</span>
                    ))}
                  </div>
                  <button
                    className="pressable w-full rounded-lg text-sm font-bold uppercase cursor-pointer border-2 mt-0.5"
                    style={{ minHeight: 56, borderColor: col, color: col, background: "var(--surface)" }}
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
      </Card>

      {iframeUrl && (
        <Takeover onClose={() => setIframeUrl(null)} accent="var(--kids)" title={iframeTitle}>
          <iframe
            src={iframeUrl}
            style={{ width: "100%", height: "100%", border: 0 }}
            title={iframeTitle}
            allow="autoplay; microphone; speaker; clipboard-write"
          />
        </Takeover>
      )}
    </>
  );
}
