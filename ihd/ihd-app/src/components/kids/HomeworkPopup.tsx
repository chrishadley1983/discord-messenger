"use client";

import { useState, useEffect, useCallback, useRef } from "react";

const CHILD_COLOURS: Record<string, string> = {
  Emmie: "#8B5CF6",
  Max: "#3B82F6",
};

const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const ACTIVITY_LABELS: Record<string, string> = {
  paper: "Practice Paper",
  times_tables: "Times Tables",
  tutor_this_week: "Tutor (This Week)",
  tutor_last_week: "Tutor (Last Week)",
  tutor_2w_ago: "Tutor (2 Wks Ago)",
  tutor_homework: "Tutor Homework",
  tutor_lesson: "Tutor Lesson",
  weak_areas: "Weak Areas",
  revision: "Revision",
  mock_exam: "Mock Exam",
  rest: "Rest",
  tutoring: "Tutoring",
};

const ACTIVITY_COLOURS: Record<string, string> = {
  paper: "#2563eb",
  times_tables: "#059669",
  tutor_this_week: "#d97706",
  tutor_last_week: "#ea580c",
  tutor_2w_ago: "#dc2626",
  tutor_homework: "#7c3aed",
  tutor_lesson: "#be185d",
  weak_areas: "#dc2626",
  revision: "#0891b2",
  mock_exam: "#4f46e5",
  rest: "#9ca3af",
  tutoring: "#be185d",
};

interface ScheduleSlot {
  student_id: string;
  day_of_week: number;
  slot_order?: number;
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

interface PracticeAttempt {
  student_id: string;
  paper_topic: string;
  paper_date: string;
  score: number;
  total: number;
  percentage: number;
  completed_at: string;
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
  wrong_words: string | string[] | null;
  time_seconds: number | null;
  created_at: string;
}

interface Paper {
  id: string;
  paper_date: string;
  topic: string;
  subject: string;
  difficulty_level: string;
  surge_url: string;
  question_count: number;
  tags?: string[];
}

interface CompletionRecord {
  student_id: string;
  activity_type: string;
  activity_date: string;
  completed: boolean;
}

interface KidsData {
  weekNumber: number;
  academicYear: string;
  spellings: SpellingRow[];
  recentResults: TestResult[];
  practice: {
    schedules: ScheduleSlot[];
    todaySchedule: ScheduleSlot[];
    tutorTopics: TutorTopic[];
    attempts: PracticeAttempt[];
    students: Student[];
    papers: Paper[];
  };
  completions: CompletionRecord[];
}

type HomeworkMode = "all" | "emmie" | "max" | "spellings";

interface HomeworkPopupProps {
  mode: HomeworkMode;
  onClose: () => void;
}

function parseWords(words: string | string[]): string[] {
  if (Array.isArray(words)) return words;
  try { return JSON.parse(words); } catch { return []; }
}

function parseWrongWords(w: string | string[] | null): string[] {
  if (!w) return [];
  if (Array.isArray(w)) return w;
  try { return JSON.parse(w); } catch { return []; }
}

function studentName(students: Student[], id: string): string {
  return students.find((s) => s.id === id)?.name || "Unknown";
}

function IframeModal({ url, title, onClose }: { url: string; title: string; onClose: () => void }) {
  const overlayRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, [onClose]);

  return (
    <div ref={overlayRef} className="fixed inset-0 z-[60] flex"
      style={{ background: "rgba(26, 23, 16, 0.5)" }}>
      <div className="bg-bg m-3 rounded-2xl shadow-xl flex flex-col overflow-hidden w-full">
        <div className="flex items-center gap-3 p-3 border-b border-border flex-shrink-0">
          <button onClick={onClose}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium bg-surface-alt border border-border cursor-pointer hover:bg-border transition-colors"
            style={{ minHeight: "44px" }}>
            &lsaquo; Back
          </button>
          <span className="text-sm text-text-mid truncate">{title}</span>
        </div>
        <iframe src={url} className="flex-1 w-full border-none" title={title} allow="autoplay; microphone; speaker; clipboard-write" />
      </div>
    </div>
  );
}

function ScheduleSection({
  schedules, students, attempts, tutorTopics, papers, completions,
  onLaunchPractice, onToggleCompletion, onLaunchActivity,
}: {
  schedules: ScheduleSlot[];
  students: Student[];
  attempts: PracticeAttempt[];
  tutorTopics: TutorTopic[];
  papers: Paper[];
  completions: CompletionRecord[];
  onLaunchPractice: () => void;
  onToggleCompletion: (studentId: string, activityType: string, date: string, completed: boolean) => void;
  onLaunchActivity: (url: string, title: string, childName?: string) => void;
}) {
  const today = new Date();
  const jsDow = today.getDay();
  const todayDow = jsDow === 0 ? 6 : jsDow - 1;
  const days = [0, 1, 2, 3, 4, 5, 6];

  const [collapsed, setCollapsed] = useState<Record<number, boolean>>(() => {
    const init: Record<number, boolean> = {};
    days.forEach((d) => { init[d] = d < todayDow; });
    return init;
  });
  const toggleDay = (dow: number) => setCollapsed((prev) => ({ ...prev, [dow]: !prev[dow] }));
  const activeDays = days.filter((d) =>
    schedules.some((s) => s.day_of_week === d && s.activity_type !== "rest")
  );

  const dateForDow = (dow: number): string => {
    const diff = dow - todayDow;
    const d = new Date(today);
    d.setDate(d.getDate() + diff);
    return d.toISOString().slice(0, 10);
  };

  const attemptsByStudentDate: Record<string, PracticeAttempt[]> = {};
  attempts.forEach((a) => {
    const key = `${a.student_id}_${a.paper_date || a.completed_at?.slice(0, 10)}`;
    if (!attemptsByStudentDate[key]) attemptsByStudentDate[key] = [];
    attemptsByStudentDate[key].push(a);
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="text-xs font-bold uppercase tracking-widest text-text-mid">
          Weekly Practice Schedule
        </div>
        <button onClick={onLaunchPractice}
          className="px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer border border-accent/30 bg-accent/10 text-accent hover:bg-accent/20 transition-colors"
          style={{ minHeight: "44px" }}>
          Launch 11PlusMate
        </button>
      </div>

      {tutorTopics.length > 0 && (
        <div className="p-3 rounded-xl bg-purple-50 border border-purple-200 mb-3">
          <div className="text-xs font-bold uppercase text-purple-700 mb-1">
            This Week&apos;s Tutor Focus
          </div>
          <div className="text-sm font-medium">
            {tutorTopics[0].topic.replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase())}
          </div>
          <div className="text-xs text-text-mid mt-0.5">
            {tutorTopics[0].subject} &middot; {tutorTopics[0].notes?.split("|")[0]?.trim().slice(0, 80)}
          </div>
        </div>
      )}

      <div className="flex flex-col gap-2">
        {activeDays.map((dow) => {
          const daySlots = schedules
            .filter((s) => s.day_of_week === dow && s.activity_type !== "rest")
            .sort((a, b) => (a.slot_order || 0) - (b.slot_order || 0));
          const isToday = dow === todayDow;
          const isPast = dow < todayDow;
          const dayDate = dateForDow(dow);
          const isCollapsed = collapsed[dow] ?? false;
          const TICKBOX_TYPES = new Set(["tutor_lesson", "tutor_homework"]);

          const byStudent: Record<string, ScheduleSlot[]> = {};
          daySlots.forEach((s) => {
            const name = studentName(students, s.student_id);
            if (!byStudent[name]) byStudent[name] = [];
            byStudent[name].push(s);
          });

          const totalSlots = daySlots.length;
          const doneCount = daySlots.filter((s) => {
            const sid = s.student_id;
            if (TICKBOX_TYPES.has(s.activity_type)) {
              return completions.some((c) => c.student_id === sid && c.activity_type === s.activity_type && c.activity_date === dayDate && c.completed);
            }
            const key = `${sid}_${dayDate}`;
            return (attemptsByStudentDate[key] || []).length > 0;
          }).length;

          return (
            <div key={dow} className="rounded-xl border" style={{
              background: isToday ? "#eff6ff" : "#f8f7f4",
              borderColor: isToday ? "#93c5fd" : "transparent",
            }}>
              <div className="flex items-center gap-2 p-3 cursor-pointer select-none"
                onClick={() => toggleDay(dow)} style={{ minHeight: "44px" }}>
                <span className="text-text-dim text-xs" style={{ transition: "transform 0.15s", transform: isCollapsed ? "rotate(-90deg)" : "rotate(0deg)" }}>
                  &#x25BE;
                </span>
                <span className={`text-sm font-bold ${isToday ? "text-blue-700" : "text-text-mid"}`}>
                  {DAY_NAMES[dow]}
                </span>
                {isToday && (
                  <span className="text-xs font-bold uppercase text-blue-500 bg-blue-100 px-1.5 py-0.5 rounded">
                    Today
                  </span>
                )}
                {isCollapsed && (
                  <span className="ml-auto text-xs text-text-dim">
                    {doneCount}/{totalSlots} done
                  </span>
                )}
              </div>

              {!isCollapsed && (
                <div className="px-3 pb-3">
                  {Object.entries(byStudent).map(([name, slots]) => {
                    const col = CHILD_COLOURS[name] || "#888";
                    const studentId = slots[0]?.student_id;
                    const dayAttempts = attemptsByStudentDate[`${studentId}_${dayDate}`] || [];
                    const usedAttemptIds = new Set<number>();

                    return (
                      <div key={name} className="mb-2.5 last:mb-0">
                        <span className="text-xs font-bold mb-1.5 block" style={{ color: col }}>{name}</span>
                        <div className="flex flex-col gap-1.5 ml-1">
                          {slots.map((s, i) => {
                            const isTickbox = TICKBOX_TYPES.has(s.activity_type);
                            const manuallyDone = isTickbox && completions.some(
                              (c) => c.student_id === s.student_id && c.activity_type === s.activity_type && c.activity_date === dayDate && c.completed
                            );

                            let bestMatch: PracticeAttempt | null = null;
                            if (!isTickbox) {
                              let bestIdx = -1;
                              let bestPct = -1;
                              dayAttempts.forEach((a, idx) => {
                                if (!usedAttemptIds.has(idx) && a.percentage > bestPct) {
                                  bestPct = a.percentage;
                                  bestIdx = idx;
                                  bestMatch = a;
                                }
                              });
                              if (bestIdx >= 0) usedAttemptIds.add(bestIdx);
                            }

                            const isDone = isTickbox ? manuallyDone : bestMatch !== null;
                            const ac = ACTIVITY_COLOURS[s.activity_type] || "#888";

                            let bgColor: string;
                            let borderColor: string;
                            let statusIcon: string;
                            let statusColor: string;

                            if (isDone) {
                              bgColor = "#f0fdf4"; borderColor = "#bbf7d0"; statusIcon = "\u2713"; statusColor = "#166534";
                            } else if (isPast) {
                              bgColor = "#fef2f2"; borderColor = "#fecaca"; statusIcon = "\u2717"; statusColor = "#dc2626";
                            } else if (isToday) {
                              bgColor = "#eff6ff"; borderColor = "#93c5fd"; statusIcon = "\u25CB"; statusColor = "#2563eb";
                            } else {
                              bgColor = "#f8f7f4"; borderColor = "#e5e2d9"; statusIcon = "\u00B7"; statusColor = "#9ca3af";
                            }

                            const getLaunchUrl = (): { url: string; title: string } | null => {
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
                                    return { url: "https://11plusmate.surge.sh/my-practice.html", title: `${ACTIVITY_LABELS[s.activity_type]} - ${targetTopic.topic}` };
                                  }
                                }
                                return { url: "https://11plusmate.surge.sh/my-practice.html", title: ACTIVITY_LABELS[s.activity_type] || s.activity_type };
                              }
                              return null;
                            };

                            const launchTarget = getLaunchUrl();
                            const isTappable = launchTarget !== null;

                            return (
                              <div key={i}
                                className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs ${isTappable ? "cursor-pointer hover:brightness-95 active:brightness-90" : ""}`}
                                style={{ background: bgColor, border: `1px solid ${borderColor}`, transition: "filter 0.1s", minHeight: "44px" }}
                                onClick={isTappable && !isTickbox ? () => onLaunchActivity(launchTarget.url, launchTarget.title, name) : undefined}
                              >
                                {isTickbox ? (
                                  <button
                                    className="w-6 h-6 rounded border-2 flex items-center justify-center flex-shrink-0 cursor-pointer transition-colors"
                                    style={{
                                      borderColor: isDone ? "#166534" : "#d1d5db",
                                      background: isDone ? "#166534" : "white",
                                    }}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      onToggleCompletion(s.student_id, s.activity_type, dayDate, !isDone);
                                    }}
                                  >
                                    {isDone && <span className="text-white text-xs font-bold">{"\u2713"}</span>}
                                  </button>
                                ) : (
                                  <span className="font-bold text-sm w-5 text-center flex-shrink-0" style={{ color: statusColor }}>
                                    {statusIcon}
                                  </span>
                                )}

                                <span className="font-semibold" style={{ color: ac }}>
                                  {ACTIVITY_LABELS[s.activity_type] || s.activity_type}
                                </span>
                                {s.duration_minutes && (
                                  <span className="text-text-dim">{s.duration_minutes}m</span>
                                )}
                                {!isTickbox && isDone && bestMatch && (
                                  <span className="ml-auto font-bold" style={{
                                    color: (bestMatch as PracticeAttempt).percentage >= 80 ? "#166534"
                                      : (bestMatch as PracticeAttempt).percentage >= 50 ? "#92400e" : "#dc2626"
                                  }}>
                                    {(bestMatch as PracticeAttempt).score}/{(bestMatch as PracticeAttempt).total} ({(bestMatch as PracticeAttempt).percentage}%)
                                  </span>
                                )}
                                {!isDone && isPast && !isTickbox && (
                                  <span className="ml-auto text-red-400 font-medium">Missed</span>
                                )}
                                {!isDone && isToday && !isTickbox && (
                                  <span className="ml-auto text-blue-400 font-medium">Due today</span>
                                )}
                                {isTappable && (
                                  <span className="text-text-dim ml-auto">{"\u25B8"}</span>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                  {isToday && (
                    <button onClick={onLaunchPractice}
                      className="mt-2 w-full py-2 rounded-lg text-xs font-semibold cursor-pointer border border-blue-300 bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors"
                      style={{ minHeight: "44px" }}>
                      Start Practice &rarr;
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SpellingsSection({
  spellings, results, weekNumber, onLaunchTest,
}: {
  spellings: SpellingRow[];
  results: TestResult[];
  weekNumber: number;
  onLaunchTest: () => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="text-xs font-bold uppercase tracking-widest text-text-mid">
          Spellings &mdash; Week {weekNumber}
        </div>
        <button onClick={onLaunchTest}
          className="px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer border border-accent/30 bg-accent/10 text-accent hover:bg-accent/20 transition-colors"
          style={{ minHeight: "44px" }}>
          Launch Spelling Test
        </button>
      </div>

      <div className="flex flex-col gap-3">
        {spellings.map((s) => {
          const words = parseWords(s.words);
          const col = CHILD_COLOURS[s.child_name] || "#888";
          const childResults = results.filter(
            (r) => r.child_name === s.child_name && r.week_number === s.week_number
          );
          const bestResult = childResults.length > 0
            ? childResults.reduce((a, b) => (a.score / a.total > b.score / b.total ? a : b))
            : null;
          const bestPct = bestResult ? bestResult.score / bestResult.total : 0;
          const wrongInBest = bestResult ? parseWrongWords(bestResult.wrong_words) : [];

          return (
            <div key={s.child_name} className="p-3 rounded-xl border"
              style={{ borderColor: col + "40", borderLeft: `4px solid ${col}` }}>
              <div className="flex items-center justify-between mb-2">
                <div>
                  <span className="text-sm font-bold" style={{ color: col }}>{s.child_name}</span>
                  <span className="text-xs text-text-dim ml-2">{s.year_group}</span>
                  {s.phoneme && <span className="text-xs text-text-mid ml-2">Phoneme: <strong>{s.phoneme}</strong></span>}
                </div>
                {bestResult && (
                  <span className="text-lg font-bold" style={{
                    color: bestPct >= 0.8 ? "#166534" : bestPct >= 0.5 ? "#92400e" : "#dc2626"
                  }}>
                    {bestResult.score}/{bestResult.total}
                  </span>
                )}
              </div>

              <div className="flex flex-wrap gap-1.5 mb-2">
                {words.map((word, i) => {
                  const isWrong = wrongInBest.map(w => w.toLowerCase()).includes(word.toLowerCase());
                  return (
                    <span key={i} className="inline-block px-2.5 py-1 rounded-lg text-xs font-medium border"
                      style={{
                        background: bestResult ? (isWrong ? "#fef2f2" : "#f0fdf4") : "#f8f7f4",
                        borderColor: bestResult ? (isWrong ? "#fca5a5" : "#bbf7d0") : "#e5e2d9",
                        color: bestResult ? (isWrong ? "#dc2626" : "#166534") : "inherit",
                      }}>
                      {word}
                    </span>
                  );
                })}
              </div>

              {childResults.length > 0 ? (
                <div className="text-xs text-text-mid">
                  {childResults.length} attempt{childResults.length !== 1 ? "s" : ""} this week
                  {bestResult?.time_seconds ? ` \u00B7 Best: ${Math.floor(bestResult.time_seconds / 60)}m ${bestResult.time_seconds % 60}s` : ""}
                </div>
              ) : (
                <div className="text-xs text-text-dim">Not tested yet this week</div>
              )}
            </div>
          );
        })}

        {spellings.length === 0 && (
          <div className="text-sm text-text-dim text-center py-6">No spellings loaded this week</div>
        )}
      </div>
    </div>
  );
}

export default function HomeworkPopup({ mode, onClose }: HomeworkPopupProps) {
  const [data, setData] = useState<KidsData | null>(null);
  const [completions, setCompletions] = useState<CompletionRecord[]>([]);
  const [iframeUrl, setIframeUrl] = useState<string | null>(null);
  const [iframeTitle, setIframeTitle] = useState("");
  const overlayRef = useRef<HTMLDivElement>(null);
  const [sessionCache, setSessionCache] = useState<Record<string, string>>({});

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch("/api/kids?action=summary");
      if (res.ok) {
        const d = await res.json();
        if (!d.error) {
          setData(d);
          setCompletions(d.completions || []);
        }
      }
    } catch { /* keep last known */ }
  }, []);

  // Pre-fetch child sessions for iframe auth
  useEffect(() => {
    const names = mode === "emmie" ? ["Emmie"] : mode === "max" ? ["Max"] : ["Emmie", "Max"];
    names.forEach(async (name) => {
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
        }
      } catch { /* ignore */ }
    });
  }, [mode]);

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

  const toggleCompletion = useCallback(async (studentId: string, activityType: string, date: string, completed: boolean) => {
    setCompletions((prev) => {
      const existing = prev.findIndex((c) => c.student_id === studentId && c.activity_type === activityType && c.activity_date === date);
      if (existing >= 0) {
        const updated = [...prev];
        updated[existing] = { ...updated[existing], completed };
        return updated;
      }
      return [...prev, { student_id: studentId, activity_type: activityType, activity_date: date, completed }];
    });
    try {
      await fetch("/api/kids", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "toggle_completion", student_id: studentId, activity_type: activityType, activity_date: date, completed }),
      });
    } catch { /* optimistic update already applied */ }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape" && !iframeUrl) onClose(); };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, [onClose, iframeUrl]);

  const allStudents = data?.practice?.students || [];
  const allSchedules = data?.practice?.schedules || [];
  const tutorTopics = data?.practice?.tutorTopics || [];
  const allAttempts = data?.practice?.attempts || [];
  const papers = data?.practice?.papers || [];

  // Filter by child when in single-child mode
  const filterStudentId = mode === "emmie" || mode === "max"
    ? allStudents.find((s) => s.name.toLowerCase() === mode)?.id
    : null;
  const students = filterStudentId ? allStudents.filter((s) => s.id === filterStudentId) : allStudents;
  const schedules = filterStudentId ? allSchedules.filter((s: ScheduleSlot) => s.student_id === filterStudentId) : allSchedules;
  const attempts = filterStudentId ? allAttempts.filter((a: PracticeAttempt) => a.student_id === filterStudentId) : allAttempts;

  // Determine child name for session lookup
  const activeChildName = mode === "emmie" ? "Emmie" : mode === "max" ? "Max" : undefined;

  const launchActivity = (url: string, title: string, childName?: string) => {
    setIframeUrl(buildIframeUrl(url, childName || activeChildName));
    setIframeTitle(title);
  };

  // Count today's completed items for the summary badge
  const todayDow = (() => { const d = new Date().getDay(); return d === 0 ? 6 : d - 1; })();
  const todaySlots = schedules.filter((s: ScheduleSlot) => s.day_of_week === todayDow && s.activity_type !== "rest");
  const todayDone = todaySlots.filter((s: ScheduleSlot) => {
    if (s.activity_type === "tutor_lesson" || s.activity_type === "tutor_homework") {
      const dayDate = new Date().toISOString().slice(0, 10);
      return completions.some((c) => c.student_id === s.student_id && c.activity_type === s.activity_type && c.activity_date === dayDate && c.completed);
    }
    return false;
  }).length;

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(26,23,16,0.5)" }}
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className="bg-white rounded-3xl shadow-2xl w-[900px] max-w-[95vw] max-h-[90vh] flex flex-col" style={{ animation: "fadeIn 0.2s ease" }}>
        <div className="flex items-center justify-between p-5 pb-3 border-b border-border flex-shrink-0">
          <div>
            <h2 className="text-lg font-bold">
              {mode === "spellings" ? "\u{1F4DD} Spellings" : mode === "emmie" ? "\u{1F984} Emmie's Homework" : mode === "max" ? "\u{1F988} Max's Homework" : "\u{1F4DA} Homework Hub"}
            </h2>
            {data && <div className="text-sm text-text-mid">Week {data.weekNumber} &middot; {data.academicYear}</div>}
          </div>
          <button onClick={onClose} className="text-2xl text-text-dim cursor-pointer p-1" style={{ minWidth: "44px", minHeight: "44px" }}>
            &times;
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {!data ? (
            <div className="flex items-center justify-center py-12">
              <div className="text-text-mid text-sm">Loading...</div>
            </div>
          ) : mode === "spellings" ? (
            <SpellingsSection
              spellings={data.spellings}
              results={data.recentResults}
              weekNumber={data.weekNumber}
              onLaunchTest={() => launchActivity("https://hadley-spelling-test.surge.sh/", "Spelling Test")}
            />
          ) : (mode === "emmie" || mode === "max") ? (
            <ScheduleSection
              schedules={schedules}
              students={students}
              attempts={attempts}
              tutorTopics={tutorTopics}
              papers={papers}
              completions={completions}
              onLaunchPractice={() => launchActivity("https://11plusmate.surge.sh/my-practice.html", "11PlusMate Practice")}
              onToggleCompletion={toggleCompletion}
              onLaunchActivity={launchActivity}
            />
          ) : (
            <div className="grid grid-cols-2 gap-6">
              <div>
                <ScheduleSection
                  schedules={schedules}
                  students={students}
                  attempts={attempts}
                  tutorTopics={tutorTopics}
                  papers={papers}
                  completions={completions}
                  onLaunchPractice={() => launchActivity("https://11plusmate.surge.sh/my-practice.html", "11PlusMate Practice")}
                  onToggleCompletion={toggleCompletion}
                  onLaunchActivity={launchActivity}
                />
              </div>
              <div>
                <SpellingsSection
                  spellings={data.spellings}
                  results={data.recentResults}
                  weekNumber={data.weekNumber}
                  onLaunchTest={() => launchActivity("https://hadley-spelling-test.surge.sh/", "Spelling Test")}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {iframeUrl && (
        <IframeModal url={iframeUrl} title={iframeTitle} onClose={() => setIframeUrl(null)} />
      )}
    </div>
  );
}

interface ChildSummary { total: number; done: number; }

export function useHomeworkSummary() {
  const [summary, setSummary] = useState<{ emmie: ChildSummary; max: ChildSummary; spellingsDue: boolean }>({
    emmie: { total: 0, done: 0 },
    max: { total: 0, done: 0 },
    spellingsDue: false,
  });

  useEffect(() => {
    async function fetch_() {
      try {
        const res = await fetch("/api/kids?action=summary");
        if (!res.ok) return;
        const data = await res.json();
        if (data.error) return;

        const schedules = data.practice?.schedules || [];
        const students = data.practice?.students || [];
        const completions = data.completions || [];
        const jsDow = new Date().getDay();
        const todayDow = jsDow === 0 ? 6 : jsDow - 1;
        const dayDate = new Date().toISOString().slice(0, 10);

        const countForChild = (childName: string): ChildSummary => {
          const sid = students.find((s: Student) => s.name === childName)?.id;
          if (!sid) return { total: 0, done: 0 };
          const slots = schedules.filter((s: ScheduleSlot) => s.student_id === sid && s.day_of_week === todayDow && s.activity_type !== "rest");
          const done = slots.filter((s: ScheduleSlot) => {
            if (s.activity_type === "tutor_lesson" || s.activity_type === "tutor_homework") {
              return completions.some((c: CompletionRecord) => c.student_id === sid && c.activity_type === s.activity_type && c.activity_date === dayDate && c.completed);
            }
            return false;
          }).length;
          return { total: slots.length, done };
        };

        const spellings = data.spellings || [];
        const results = data.recentResults || [];
        const spellingsDue = spellings.length > 0 && spellings.some((s: SpellingRow) => {
          const childResults = results.filter((r: TestResult) => r.child_name === s.child_name && r.week_number === s.week_number);
          return childResults.length === 0;
        });

        setSummary({
          emmie: countForChild("Emmie"),
          max: countForChild("Max"),
          spellingsDue,
        });
      } catch { /* ignore */ }
    }
    fetch_();
  }, []);

  return summary;
}
