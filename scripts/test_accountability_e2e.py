"""Comprehensive E2E test for the accountability tracker.

Tests backend API, dashboard proxy, dashboard UI components, and data flow.
Assumes Hadley API on :8100 and Dashboard on :5000 are running.
"""

import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()
import httpx

API = "http://localhost:8100"
DASHBOARD = "http://localhost:5000"
H = {"x-api-key": os.getenv("HADLEY_AUTH_KEY", "")}
PASS = 0
FAIL = 0


def test(name, fn):
    global PASS, FAIL
    try:
        result = fn()
        if result:
            print(f"  PASS  {name}")
            PASS += 1
        else:
            print(f"  FAIL  {name} - returned falsy")
            FAIL += 1
    except Exception as e:
        print(f"  FAIL  {name} - {e}")
        FAIL += 1


print("=== BACKEND API TESTS ===\n")

# 1. Goals list
print("-- Goals Endpoints --")
start = time.time()
r = httpx.get(f"{API}/accountability/goals", headers=H, timeout=30)
elapsed = time.time() - start
test(f"GET /goals returns 200 ({elapsed:.1f}s)", lambda: r.status_code == 200)
data = r.json()
test(f"GET /goals returns {data['count']} goals", lambda: data["count"] == 4)
test("GET /goals response < 5s", lambda: elapsed < 5)

for g in data["goals"]:
    test(f'Goal "{g["title"]}" has computed', lambda g=g: "computed" in g)
    test(f'Goal "{g["title"]}" has today_value', lambda g=g: "today_value" in g.get("computed", {}))

# 2. Goal detail with source history
print("\n-- Goal Detail (source history) --")
steps_goals = [g for g in data["goals"] if "Steps" in g["title"]]
if steps_goals:
    sg = steps_goals[0]
    start = time.time()
    r2 = httpx.get(f"{API}/accountability/goals/{sg['id']}?days=31", headers=H, timeout=30)
    elapsed2 = time.time() - start
    test(f"GET /goals/{{id}} returns 200 ({elapsed2:.1f}s)", lambda: r2.status_code == 200)
    detail = r2.json()
    test("Detail has progress list", lambda: isinstance(detail.get("progress"), list))
    prog_count = len(detail.get("progress", []))
    test(f"Steps progress from source ({prog_count} entries)", lambda: prog_count > 0)
    if detail.get("progress"):
        test("Progress entries have date+value", lambda: all("date" in p and "value" in p for p in detail["progress"]))

# Weight goal detail
weight_goals = [g for g in data["goals"] if g.get("metric") == "kg"]
if weight_goals:
    wg = weight_goals[0]
    r3 = httpx.get(f"{API}/accountability/goals/{wg['id']}?days=31", headers=H, timeout=30)
    test("Weight goal detail 200", lambda: r3.status_code == 200)
    w_detail = r3.json()
    wp_count = len(w_detail.get("progress", []))
    test(f"Weight history from source ({wp_count} entries)", lambda: wp_count > 0)

# Boolean habit
bool_goals = [g for g in data["goals"] if g.get("metric") == "boolean"]
test("Boolean habit exists", lambda: len(bool_goals) > 0)

# 3. Progress logging
print("\n-- Progress Logging --")
if bool_goals:
    r4 = httpx.post(
        f"{API}/accountability/goals/{bool_goals[0]['id']}/progress",
        headers={**H, "Content-Type": "application/json"},
        json={"value": 1, "source": "manual"},
        timeout=10,
    )
    test("Boolean toggle (value=1) returns 200", lambda: r4.status_code == 200)

# 4. Mood
print("\n-- Mood Endpoints --")
r5 = httpx.post(
    f"{API}/accountability/mood",
    headers={**H, "Content-Type": "application/json"},
    json={"score": 8, "note": "E2E test"},
    timeout=10,
)
test("POST /mood returns 200", lambda: r5.status_code == 200)
test("POST /mood status=logged", lambda: r5.json().get("status") == "logged")

r6 = httpx.get(f"{API}/accountability/mood", headers=H, timeout=10)
test("GET /mood returns 200", lambda: r6.status_code == 200)
test("GET /mood has today score=8", lambda: r6.json().get("today", {}).get("score") == 8)

r7 = httpx.get(f"{API}/accountability/mood/history?days=7", headers=H, timeout=10)
test("GET /mood/history returns 200", lambda: r7.status_code == 200)
test("Mood history has entries", lambda: r7.json().get("count", 0) > 0)

# 5. Journal
print("\n-- Journal Endpoints --")
r8 = httpx.post(
    f"{API}/accountability/journal",
    headers={**H, "Content-Type": "application/json"},
    json={"content": "E2E test journal entry."},
    timeout=10,
)
test("POST /journal returns 200", lambda: r8.status_code == 200)
test("POST /journal status=saved", lambda: r8.json().get("status") == "saved")

r9 = httpx.get(f"{API}/accountability/journal", headers=H, timeout=10)
test("GET /journal returns 200", lambda: r9.status_code == 200)
test("GET /journal has today entry", lambda: r9.json().get("entry") is not None)

r10 = httpx.get(f"{API}/accountability/journal/history?days=7", headers=H, timeout=10)
test("GET /journal/history returns 200", lambda: r10.status_code == 200)

# 6. Summary
print("\n-- Summary --")
start = time.time()
r11 = httpx.get(f"{API}/accountability/summary", headers=H, timeout=30)
elapsed3 = time.time() - start
test(f"GET /summary returns 200 ({elapsed3:.1f}s)", lambda: r11.status_code == 200)
s = r11.json()
test("Summary has goals", lambda: s.get("count", 0) > 0)
test("Summary has mood", lambda: s.get("mood") is not None)
test("Summary has journal", lambda: s.get("journal") is not None)

# 7. Auto-update
print("\n-- Auto-Update --")
r12 = httpx.post(f"{API}/accountability/auto-update", headers=H, timeout=30)
test("POST /auto-update returns 200", lambda: r12.status_code == 200)

# 8. Dashboard proxy
print("\n-- Dashboard Proxy --")
r13 = httpx.get(f"{DASHBOARD}/api/hadley/proxy/accountability/goals", timeout=15)
test("Proxy goals returns 200", lambda: r13.status_code == 200)
test("Proxy goals has data", lambda: r13.json().get("count", 0) > 0)

r14 = httpx.get(f"{DASHBOARD}/api/hadley/proxy/accountability/mood", timeout=10)
test("Proxy mood returns 200", lambda: r14.status_code == 200)

r15 = httpx.get(f"{DASHBOARD}/api/hadley/proxy/accountability/journal", timeout=10)
test("Proxy journal returns 200", lambda: r15.status_code == 200)

# 9. Dashboard UI components
print("\n-- Dashboard UI --")
r16 = httpx.get(DASHBOARD, timeout=10)
html = r16.text
test("Dashboard loads", lambda: r16.status_code == 200)
test("Goals nav in sidebar", lambda: 'data-route="/goals"' in html)

r17 = httpx.get(f"{DASHBOARD}/static/js/app.js", timeout=10)
js = r17.text
test("GoalsView in JS", lambda: "GoalsView" in js)
test("showGoalDetail method", lambda: "showGoalDetail" in js)
test("toggleBoolean method", lambda: "toggleBoolean" in js)
test("loadMood method", lambda: "loadMood" in js)
test("loadJournal method", lambda: "loadJournal" in js)
test("mood-widget div", lambda: "mood-widget" in js)
test("journal-widget div", lambda: "journal-widget" in js)
test("Boolean metric option", lambda: "boolean" in js and "Yes/No" in js)
test("Card onclick", lambda: "showGoalDetail" in js)
test("stopPropagation on buttons", lambda: "event.stopPropagation()" in js)
test("onMetricChange for boolean", lambda: "onMetricChange" in js)

r18 = httpx.get(f"{DASHBOARD}/static/css/main.css", timeout=10)
css = r18.text
test("Goal detail CSS", lambda: ".goal-detail" in css)
test("Mood widget CSS", lambda: ".mood-widget" in css)
test("Journal widget CSS", lambda: ".journal-widget" in css)
test("Boolean toggle CSS", lambda: ".btn-success" in css)
test("Mood buttons CSS", lambda: ".mood-btn" in css)
test("Extras grid CSS", lambda: ".accountability-extras" in css)

# 10. Skills + Infrastructure
print("\n-- Skills + Infrastructure --")
from pathlib import Path

skills = ["accountability-update", "accountability-weekly", "accountability-monthly", "mood-log", "journal-log"]
for skill in skills:
    path = Path(f"domains/peterbot/wsl_config/skills/{skill}/SKILL.md")
    test(f"Skill {skill} exists", lambda p=path: p.exists())

test("SCHEDULE.md has weekly", lambda: "accountability-weekly" in Path("domains/peterbot/wsl_config/SCHEDULE.md").read_text())
test("SCHEDULE.md has monthly", lambda: "accountability-monthly" in Path("domains/peterbot/wsl_config/SCHEDULE.md").read_text())

test("Migration exists", lambda: Path("supabase/migrations/20260401_mood_journal.sql").exists())

claude_md = Path("domains/peterbot/wsl_config/CLAUDE.md").read_text(encoding="utf-8")
test("CLAUDE.md mentions mood", lambda: "/accountability/mood" in claude_md)
test("CLAUDE.md mentions journal", lambda: "/accountability/journal" in claude_md)
test("CLAUDE.md mentions boolean", lambda: "boolean" in claude_md)

print(f"\n{'=' * 50}")
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print(f"{'=' * 50}")

sys.exit(1 if FAIL > 0 else 0)
