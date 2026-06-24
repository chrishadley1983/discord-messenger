import { NextRequest, NextResponse } from "next/server";
import { readFile, writeFile, mkdir } from "fs/promises";
import { join } from "path";

const SUPABASE_URL = "https://modjoikyuhqzouxvieua.supabase.co";
const SUPABASE_KEY = process.env.SUPABASE_ANON_KEY || "";

const SB_HEADERS = {
  apikey: SUPABASE_KEY,
  Authorization: `Bearer ${SUPABASE_KEY}`,
};

// Local file for storing manual completions (tutor lesson/homework ticks)
const DATA_DIR = join(process.cwd(), ".data");
const COMPLETIONS_FILE = join(DATA_DIR, "completions.json");

interface CompletionRecord {
  student_id: string;
  activity_type: string;
  activity_date: string;
  completed: boolean;
}

async function loadCompletions(): Promise<CompletionRecord[]> {
  try {
    const raw = await readFile(COMPLETIONS_FILE, "utf-8");
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

async function saveCompletions(records: CompletionRecord[]) {
  await mkdir(DATA_DIR, { recursive: true });
  await writeFile(COMPLETIONS_FILE, JSON.stringify(records, null, 2));
}

async function sbGet(path: string) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    headers: SB_HEADERS,
    signal: AbortSignal.timeout(5000),
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}

async function fetch11PlusMate() {
  try {
    const res = await fetch(
      `${SUPABASE_URL}/functions/v1/practice-dashboard?family_code=hadley`,
      {
        headers: { Authorization: `Bearer ${SUPABASE_KEY}` },
        signal: AbortSignal.timeout(8000),
        cache: "no-store",
      }
    );
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

// Replicates the spelling test app's getCurrentWeek() logic
function getSpellingWeek(): number {
  const TERM_DATES: [Date, Date][] = [
    [new Date(2025, 8, 4), new Date(2025, 9, 24)],   // Autumn 1
    [new Date(2025, 10, 3), new Date(2025, 11, 19)],  // Autumn 2
    [new Date(2026, 0, 5), new Date(2026, 1, 13)],    // Spring 1
    [new Date(2026, 1, 23), new Date(2026, 2, 27)],   // Spring 2
    [new Date(2026, 3, 13), new Date(2026, 4, 22)],   // Summer 1
    [new Date(2026, 5, 1), new Date(2026, 6, 22)],    // Summer 2
  ];
  const SPELLING_WEEK_OFFSET = -3;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  let teachingWeek = 0;
  for (const [termStart, termEnd] of TERM_DATES) {
    const monday = new Date(termStart);
    const dayOfWeek = monday.getDay();
    if (dayOfWeek !== 1) {
      monday.setDate(monday.getDate() + ((7 - dayOfWeek + 1) % 7));
    }
    const endDate = today < termEnd ? today : termEnd;
    while (monday <= endDate) {
      teachingWeek++;
      monday.setDate(monday.getDate() + 7);
    }
    if (today <= termEnd) break;
  }
  return Math.max(1, Math.min(36, teachingWeek + SPELLING_WEEK_OFFSET));
}

export async function GET(request: NextRequest) {
  const action = request.nextUrl.searchParams.get("action") || "summary";

  try {
    if (action === "summary" || action === "spellings") {
      const spellingWeek = getSpellingWeek();
      const academicYear = "2025-26";

      // Fetch all data in parallel
      const [emmieSpellings, maxSpellings, results, practiceData, completions] = await Promise.all([
        sbGet(
          `school_spellings?academic_year=eq.${academicYear}&week_number=eq.${spellingWeek}&child_name=eq.Emmie&select=*`
        ),
        sbGet(
          `school_spellings?academic_year=eq.${academicYear}&child_name=eq.Max&select=*&order=week_number.desc&limit=1`
        ),
        sbGet(
          `spelling_test_results?select=*&order=created_at.desc&limit=20`
        ),
        fetch11PlusMate(),
        loadCompletions(),
      ]);

      const spellings = [
        ...((emmieSpellings as unknown[]) || []),
        ...((maxSpellings as unknown[]) || []),
      ];

      // Extract schedule and tutor topics from 11PlusMate
      // API uses 0=Mon,...,6=Sun; JS getDay() uses 0=Sun,...,6=Sat
      const jsDow = new Date().getDay();
      const todayDow = jsDow === 0 ? 6 : jsDow - 1;
      const schedules = practiceData?.schedules || [];
      const tutorTopics = practiceData?.tutor_topics || [];
      const attempts = practiceData?.attempts || [];
      const students = practiceData?.students || [];
      const papers = practiceData?.papers || [];

      const todaySchedule = schedules
        .filter((s: { day_of_week: number }) => s.day_of_week === todayDow)
        .sort((a: { slot_order: number }, b: { slot_order: number }) => a.slot_order - b.slot_order);

      return NextResponse.json({
        weekNumber: spellingWeek,
        academicYear,
        spellings,
        recentResults: results || [],
        completions,
        practice: {
          schedules,
          todaySchedule,
          tutorTopics,
          attempts,
          students,
          papers,
          knowledgeGaps: practiceData?.knowledge_gaps || [],
          timesTablesAccuracy: practiceData?.times_tables_accuracy || [],
        },
      });
    }

    return NextResponse.json({ error: "Unknown action" }, { status: 400 });
  } catch (e) {
    return NextResponse.json(
      { error: "Kids data unavailable", detail: String(e) },
      { status: 200 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    if (body.action === "get_child_session") {
      const { child_name } = body;
      if (!child_name) {
        return NextResponse.json({ error: "Missing child_name" }, { status: 400 });
      }

      // Fetch student data (includes child_pin) from practice-dashboard
      const dashData = await fetch11PlusMate();
      if (!dashData || !dashData.students) {
        return NextResponse.json({ error: "Could not fetch student data" }, { status: 500 });
      }

      const student = dashData.students.find(
        (s: { name: string; child_pin: string }) =>
          s.name.toLowerCase() === child_name.toLowerCase()
      );
      if (!student || !student.child_pin) {
        return NextResponse.json({ error: "Student not found or no PIN set" }, { status: 404 });
      }

      // Create a session via practice-auth child-login
      const authRes = await fetch(`${SUPABASE_URL}/functions/v1/practice-auth`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${SUPABASE_KEY}`,
        },
        body: JSON.stringify({
          action: "child-login",
          family_code: "HADLEY",
          child_name: student.name,
          child_pin: student.child_pin,
        }),
      });

      const session = await authRes.json();
      return NextResponse.json(session);
    }

    if (body.action === "get_allocations") {
      const { session_token, student_id } = body;
      if (!session_token || !student_id) {
        return NextResponse.json({ error: "Missing session_token or student_id" }, { status: 400 });
      }

      try {
        const res = await fetch(
          `${SUPABASE_URL}/functions/v1/allocate-practice?session_token=${encodeURIComponent(session_token)}&student_id=${encodeURIComponent(student_id)}`,
          {
            headers: { Authorization: `Bearer ${SUPABASE_KEY}` },
            signal: AbortSignal.timeout(10000),
          }
        );
        const data = await res.json();
        return NextResponse.json(data);
      } catch {
        return NextResponse.json({ error: "Could not fetch allocations" }, { status: 500 });
      }
    }

    if (body.action === "toggle_completion") {
      const { student_id, activity_type, activity_date, completed } = body;
      const records = await loadCompletions();

      const idx = records.findIndex(
        (r) => r.student_id === student_id && r.activity_type === activity_type && r.activity_date === activity_date
      );

      if (idx >= 0) {
        records[idx].completed = completed;
      } else {
        records.push({ student_id, activity_type, activity_date, completed });
      }

      // Prune old records (keep last 30 days)
      const cutoff = new Date();
      cutoff.setDate(cutoff.getDate() - 30);
      const cutoffStr = cutoff.toISOString().slice(0, 10);
      const pruned = records.filter((r) => r.activity_date >= cutoffStr);

      await saveCompletions(pruned);
      return NextResponse.json({ ok: true });
    }

    return NextResponse.json({ error: "Unknown action" }, { status: 400 });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
