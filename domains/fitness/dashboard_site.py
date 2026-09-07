"""Generator for Chris's reset-cut dashboard.

Static, passcode-encrypted (AES-GCM), surge-hosted single page. Pulls live data
from the fitness service + Withings body comp, asks the local AI coach (Pete) for
an expert summary via the jobs-channel, encrypts the whole payload with the
DASHBOARD_PASSCODE, injects it into the template and deploys to surge.

Rebuilt daily (see bot.py) so the static snapshot stays current.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse as _url
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from domains.fitness import service as fit
from domains.fitness.programme_generator import generate_week, session_to_dict
from domains.fitness.trend import compute_trend
from logger import logger

UK_TZ = ZoneInfo("Europe/London")
JOBS_CHANNEL_URL = "http://127.0.0.1:8103/job"
PBKDF2_ITERS = 150_000
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
TEMPLATE = Path(__file__).with_name("dashboard_template.html")
# Fixed, shared path (NOT tempdir) so the bot/build process and the HadleyAPI
# service — separate processes with different %TEMP% — read/write the same file.
LOCAL_HTML = Path(__file__).resolve().parents[2] / "data" / "reset-cut-dashboard.html"
LOCAL_PAGES_DIR = LOCAL_HTML.parent / "session-pages"   # built session pages (LAN mirror)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


# ── helpers ────────────────────────────────────────────────────────────

def _yt_id(url: str | None) -> str | None:
    """Extract a YouTube video id from a watch URL; None for search/other."""
    if not url or "watch?v=" not in url:
        return None
    try:
        q = _url.urlparse(url).query
        vid = _url.parse_qs(q).get("v", [None])[0]
        return vid if vid and len(vid) >= 8 else None
    except Exception:
        return None


def _round(v, n=1):
    try:
        return round(float(v), n)
    except (TypeError, ValueError):
        return None


async def _latest_bodyfat() -> dict | None:
    """Most recent Withings body-fat reading (fat ratio %, fat/lean kg)."""
    try:
        from domains.nutrition.services import withings as W
        W._load_tokens(quiet=True)
        start = int((datetime.now() - timedelta(days=180)).timestamp())
        end = int(datetime.now().timestamp())

        async def _call():
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.post(
                    "https://wbsapi.withings.net/measure",
                    data={"action": "getmeas", "meastypes": "1,5,6,8", "category": 1,
                          "startdate": start, "enddate": end},
                    headers={"Authorization": f"Bearer {W._tokens['access']}"},
                )
                return r.json()

        data = await _call()
        if data.get("status") != 0 and await W._refresh_token():
            data = await _call()
        grps = sorted(data.get("body", {}).get("measuregrps", []), key=lambda g: g["date"])
        for g in reversed(grps):
            vals = {m["type"]: m["value"] * (10 ** m["unit"]) for m in g["measures"]}
            if 6 in vals:  # fat ratio %
                return {
                    "pct": _round(vals[6]),
                    "fat_kg": _round(vals.get(8)),
                    "lean_kg": _round(vals.get(5)),
                    "date": datetime.fromtimestamp(g["date"]).strftime("%d %b"),
                }
    except Exception as e:
        logger.warning(f"Dashboard: body-fat fetch failed: {e}")
    return None


async def _video_ok(vid: str, client: httpx.AsyncClient):
    """True/False if a YouTube video is available+embeddable; None on a transient error."""
    try:
        r = await client.get("https://www.youtube.com/oembed",
                             params={"format": "json", "url": f"https://www.youtube.com/watch?v={vid}"})
        return r.status_code == 200
    except Exception:
        return None


async def _yt_search_ids(query: str, client: httpx.AsyncClient) -> list[str]:
    """Scrape YouTube search results for candidate video ids, in result order."""
    try:
        r = await client.get("https://www.youtube.com/results",
                             params={"search_query": query, "hl": "en", "gl": "US"})
        ids, seen = [], set()
        for m in re.findall(r'"videoId":"([0-9A-Za-z_-]{11})"', r.text):
            if m not in seen:
                seen.add(m)
                ids.append(m)
        return ids[:12]
    except Exception:
        return []


async def _find_working_video(name: str, slug: str, client: httpx.AsyncClient):
    """Search YouTube for the exercise and loop through results until one is
    available. Tries a few query phrasings before giving up."""
    base = re.sub(r"\(.*?\)", "", name or slug).strip()
    extra = " bodyweight" if ("(BW)" in (name or "") or slug.startswith("bw-")) else ""
    for q in (f"{base} exercise how to{extra}", f"how to {base}{extra}", f"{base}{extra} proper form"):
        for vid in await _yt_search_ids(q, client):
            if await _video_ok(vid, client) is True:
                return vid
    return None


async def _persist_video_url(slug: str, url, client: httpx.AsyncClient) -> None:
    """Write a healed (or cleared) video_url back to fitness_exercises so it sticks."""
    if not (SUPABASE_URL and SUPABASE_KEY):
        return
    try:
        await client.patch(f"{SUPABASE_URL}/rest/v1/fitness_exercises",
                          params={"slug": f"eq.{slug}"},
                          headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                                   "Content-Type": "application/json"},
                          json={"video_url": url})
    except Exception as e:
        logger.warning(f"Dashboard: failed to persist video for {slug}: {e}")


async def _heal_dead_videos(library: dict) -> None:
    """Make sure every exercise demo video actually plays. Each video_url is checked
    via YouTube oEmbed (cached 7-day in data/yt_availability.json). If one is dead,
    search YouTube for the exercise and loop through results until an available video
    is found, then use it AND persist it back to fitness_exercises so the fix sticks.
    If nothing playable is found, hide the embed (null video_url) rather than render a
    broken 'Video unavailable' box. Transient network errors fail open (keep the video)."""
    cache_path = LOCAL_HTML.parent / "yt_availability.json"
    try:
        cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    except Exception:
        cache = {}
    now = datetime.now().timestamp()
    ttl = 7 * 86400

    async with httpx.AsyncClient(
        timeout=12, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en", "Cookie": "CONSENT=YES+cb"},
    ) as c:
        async def ok(vid):
            ent = cache.get(vid)
            if ent and (now - ent.get("ts", 0)) <= ttl:
                return ent["ok"]
            res = await _video_ok(vid, c)
            if res is None:
                return True  # transient — fail open, don't cache
            cache[vid] = {"ok": res, "ts": now}
            return res

        healed, hidden = [], []
        for slug, row in library.items():
            vid = _yt_id(row.get("video_url"))
            if not vid or await ok(vid):
                continue
            # dead → search + loop until a working replacement is found
            new = await _find_working_video(row.get("name", slug), slug, c)
            if new:
                url = f"https://www.youtube.com/watch?v={new}"
                row["video_url"] = url
                cache[new] = {"ok": True, "ts": now}
                await _persist_video_url(slug, url, c)
                healed.append(f"{slug}->{new}")
            else:
                row["video_url"] = None
                hidden.append(slug)

    try:
        cache_path.write_text(json.dumps(cache))
    except Exception:
        pass
    if healed:
        logger.info(f"Dashboard: healed {len(healed)} dead exercise video(s): {', '.join(healed)}")
    if hidden:
        logger.info(f"Dashboard: hid {len(hidden)} unfixable exercise video(s): {', '.join(hidden)}")


# Three ~10-min mobility routines, rotated by day. Hip/sciatica-biased to suit
# Chris's niggle. Slugs all exist in fitness_exercises with demo videos.
MOBILITY_ROUTINES = [  # each ~10 min (600s)
    ("Hips & sciatica", [("couch-stretch", 120), ("pigeon-pose", 180),
                         ("worlds-greatest-stretch", 120), ("glute-bridge", 90), ("childs-pose", 90)]),
    ("Spine & posture", [("cat-cow", 90), ("thoracic-twist", 120), ("bird-dog", 120),
                         ("worlds-greatest-stretch", 120), ("neck-rolls", 60), ("childs-pose", 90)]),
    ("Full-body reset", [("neck-rolls", 45), ("cat-cow", 90), ("worlds-greatest-stretch", 120),
                         ("couch-stretch", 120), ("pigeon-pose", 150), ("childs-pose", 75)]),
]


def _fmt_dur(secs: int) -> str:
    return f"{secs // 60}:{secs % 60:02d} min" if secs >= 60 else f"{secs}s"


def _mobility_rotation(library: dict, day_index: int) -> dict:
    idx = day_index % len(MOBILITY_ROUTINES)
    name, moves = MOBILITY_ROUTINES[idx]
    out, total = [], 0
    for slug, secs in moves:
        lib = library.get(slug, {})
        total += secs
        out.append({"name": lib.get("name", slug), "detail": _fmt_dur(secs),
                    "cue": lib.get("form_cue"), "video_id": _yt_id(lib.get("video_url"))})
    return {"name": name, "total_min": round(total / 60), "moves": out,
            "rotation": [r[0] for r in MOBILITY_ROUTINES], "rotation_today": idx}


def _status_from_delta(delta_pct, good_up=True):
    if delta_pct is None:
        return "neutral"
    if good_up:
        return "good" if delta_pct >= 0 else "watch"
    return "good" if delta_pct <= 0 else "watch"


# ── AI summary via jobs-channel ────────────────────────────────────────

async def _completed_days_nutrition(days: int = 7) -> dict:
    """Per-day calorie/protein totals for the last N COMPLETED days (yesterday
    back). The daily build runs early morning — before breakfast is logged —
    so 'today' is always a partial snapshot at build time. Logging adherence
    must be judged on these completed days, never on today's zeros."""
    today = datetime.now(UK_TZ).date()
    start = today - timedelta(days=days)
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            f"{fit.SUPABASE_URL}/rest/v1/nutrition_logs",
            headers=fit._read_headers(),
            params={
                "select": "logged_at,calories,protein_g",
                "and": f"(logged_at.gte.{start.isoformat()}T00:00:00,"
                       f"logged_at.lt.{today.isoformat()}T00:00:00)",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
    by_day: dict[str, dict] = {}
    for r in rows:
        d = str(r["logged_at"])[:10]
        agg = by_day.setdefault(d, {"cal": 0.0, "pro": 0.0})
        agg["cal"] += float(r.get("calories") or 0)
        agg["pro"] += float(r.get("protein_g") or 0)
    out = []
    for i in range(days, 0, -1):
        d = today - timedelta(days=i)
        v = by_day.get(d.isoformat())
        out.append({
            "date": d.isoformat(), "day": DAY_NAMES[d.weekday()],
            "calories": round(v["cal"]) if v else 0,
            "protein_g": round(v["pro"], 1) if v else 0,
            "logged": v is not None,
        })
    return {"days": out, "unlogged_count": sum(1 for r in out if not r["logged"])}


async def _ai_summary(facts: dict) -> str:
    g = facts.get("goal", {})
    prompt = (
        "You are Pete, Chris's expert personal trainer and nutrition coach. "
        "Write a concise summary (4–6 sentences, plain text, NO markdown headings) "
        "of his cut using the data below. Non-negotiable structure:\n"
        "1. LEAD with the honest position: the on_track_label verdict, the gap vs this "
        "week's line (plan.gap_vs_line_kg), and required vs actual rate "
        "(plan.required_kg_per_week vs hero.slope). If plan.projected_finish_date or "
        "projected_end_weight show the current rate missing the deadline, SAY SO with the "
        "numbers — e.g. 'at this rate you arrive in March, not December'. Softening words "
        "('a touch', 'roughly', 'drifting', 'more or less on track') are banned when the "
        "tier is behind/well_behind/off_track.\n"
        "2. Name the primary cause bluntly — if the data shows unlogged days or a stall, "
        "that IS the story, not a footnote. Judge logging and intake ONLY on "
        "nutrition_completed_days (the last 7 finished days): logged=false days are the "
        "genuinely unlogged ones; logged=true days show real intake vs targets. "
        "TIMING RULE: this build runs early morning, so the 'today' metrics are a "
        "same-moment partial snapshot and normally read 0 before breakfast is logged — "
        "NEVER describe today's zeros as missed logging or an unlogged day.\n"
        "3. ONE corrective focus for this week, with a number attached (a calorie line, a "
        "protein floor, a step count).\n"
        "4. One genuine positive, briefly — it must not outweigh the gap.\n"
        f"Frame around his CURRENT goal phase (\"{g.get('label','')}\": {g.get('focus','')}) "
        "and use the protein target from the data — never invent a different one. "
        "Tone: a direct coach who respects Chris enough to tell him the truth. He is "
        "tapering sertraline (GP-supervised): no shame, no catastrophising, no 'you failed' "
        "framing — the numbers are the problem, not his character; walking stays framed as "
        "stress relief. Honest and warm are not opposites — be both. When done, call the "
        "reply tool with the job_id and your summary text only.\n\n"
        f"DATA:\n{json.dumps(facts, default=str)}"
    )
    try:
        async with httpx.AsyncClient(timeout=200) as c:
            r = await c.post(JOBS_CHANNEL_URL,
                             json={"context": prompt, "skill": "fitness-dashboard-summary"})
            if r.status_code == 200:
                txt = (r.json().get("response") or "").strip()
                if txt and txt.upper() != "NO_REPLY" and len(txt) > 40:
                    return txt
            logger.warning(f"Dashboard AI summary: channel returned {r.status_code}/empty")
    except Exception as e:
        logger.warning(f"Dashboard AI summary via channel failed: {e}")
    # Fallback — deterministic and just as honest as the AI version.
    h = facts.get("hero", {})
    p = facts.get("plan") or {}
    protein_line = g.get("protein_note") or (
        f"hold protein around {g.get('protein_target','?')}g"
    )
    parts = [
        f"{h.get('on_track_label','Tracking')}: trend {h.get('current_weight','?')} kg vs "
        f"{h.get('target_this_week','?')} kg on this week's line"
    ]
    if p.get("gap_vs_line_kg") is not None:
        parts[0] += f" ({p['gap_vs_line_kg']:+.1f} kg)"
    if p.get("required_kg_per_week") is not None:
        actual = h.get("slope")
        parts.append(
            f"Hitting {h.get('target_weight','?')} kg by the deadline needs "
            f"{p['required_kg_per_week']:.2f} kg/wk from here; actual is "
            f"{actual if actual not in (None, '—') else 'flat'} kg/wk"
        )
    if p.get("projected_end_weight") is not None:
        parts.append(f"At the current rate you finish at {p['projected_end_weight']} kg")
    parts.append(f"This week: hit the calorie line daily and {protein_line}")
    parts.append("The daily walk stays — for your head as much as the deficit")
    return ". ".join(parts) + "."


# ── data assembly ──────────────────────────────────────────────────────

async def _training_payload(programme: dict | None, library: dict) -> dict | None:
    """Training tab data for the plan-driven programme: this week, next session,
    next hard cardio, recent sessions, per-exercise load series, cardio history."""
    if not programme or programme.get("split") != "plan":
        return None
    from domains.fitness import training_plan as tp
    from datetime import timedelta
    try:
        plan, row = await fit.get_plan_or_default()
        week = await fit.training_week_summary()
        nxt = await fit.next_session_bundle()
        wk = fit.week_number(programme)
        last_hard = await fit.last_hard_cardio()
        next_hard = tp.next_cardio_hard(plan, last_hard, wk)
        workouts = await fit.get_workouts_with_sets(56)
        today = fit._today()
        cardio = await fit.get_cardio_in_range(today - timedelta(days=56), today)
        history_by_slug = await fit.get_sets_history(days=84)
    except Exception as e:
        logger.warning(f"Dashboard: training payload failed: {e}")
        return None

    def _fmt_sets(sets):
        by = {}
        for s in sets:
            slug = (s.get("exercise") or {}).get("slug", "?")
            by.setdefault(slug, []).append(s)
        out = []
        for slug, ss in by.items():
            name = library.get(slug, {}).get("name", slug)
            w = [float(x["weight_kg"]) for x in ss if x.get("weight_kg") is not None]
            reps = [str(x["reps"]) + ("✗" if x.get("failed") else "") for x in ss if x.get("reps") is not None]
            holds = [f"{x['hold_s']}s" for x in ss if x.get("hold_s")]
            detail = (f"{max(w):g} kg · " if w else "") + ("/".join(reps) if reps else "/".join(holds))
            out.append({"name": name, "detail": detail})
        return out

    sessions = [{
        "date": s["session_date"], "type": s["session_type"],
        "label": (plan.get("sessions", {}).get(s["session_type"]) or {}).get("label", s["session_type"].replace("_", " ").title()),
        "rpe": s.get("rpe"), "duration_min": s.get("duration_min"), "source": s.get("source", "peter"),
        "garmin": bool(s.get("garmin_activity_id")), "exercises": _fmt_sets(s.get("sets") or []),
    } for s in workouts if s["session_type"] not in ("mobility", "rest", "cardio")]

    load_series = []
    for slug, hist in history_by_slug.items():
        pts = []
        for h in reversed(hist):
            ws = [float(x["weight_kg"]) for x in h["sets"] if x.get("weight_kg") is not None]
            rs = [int(x["reps"]) for x in h["sets"] if x.get("reps") is not None]
            if ws:
                pts.append({"date": h["date"], "kg": max(ws), "reps": min(rs) if rs else None,
                            "failed": any(x.get("failed") for x in h["sets"])})
        if pts:
            load_series.append({"slug": slug, "name": library.get(slug, {}).get("name", slug), "points": pts})
    load_series.sort(key=lambda x: (-len(x["points"]), x["name"]))

    def _peak(c):
        for b in (c.get("protocol") or []):
            if b.get("phase") == "peak":
                return b.get("seconds")
        return None
    cardio_hist = [{
        "date": c["session_date"], "modality": c["modality"], "intensity": c["intensity"],
        "minutes": c.get("duration_min"), "avg_hr": c.get("avg_hr"), "calories": c.get("calories"),
        "peak_seconds": _peak(c), "level": c.get("work_level") or c.get("peak_level"),
        "limiter": c.get("limiter"), "pain": bool(c.get("pain_flag")), "source": c.get("source", "peter"),
        "garmin": bool(c.get("garmin_activity_id")),
    } for c in cardio]

    return {
        "plan_version": row["version"] if row else None,
        "plan_name": plan.get("name"),
        "week": week,
        "next": {
            "session_type": nxt["session_type"], "label": nxt.get("label"), "status": nxt.get("status"),
            "order_variant": nxt.get("order_variant"), "rest_gap_ok": nxt.get("rest_gap_ok"),
            "days_since_last_strength": nxt.get("days_since_last_strength"),
            "duration_min": nxt.get("duration_min"), "page": nxt.get("page"),
            "exercises": [{"name": e["name"], "sets": e["sets"], "target_reps": e["target_reps"],
                           "weight_kg": e["weight_kg"], "action": e["action"], "reason": e["reason"],
                           "last_kg": (e.get("last") or {}).get("top_weight")} for e in nxt.get("exercises", [])],
        },
        "next_hard": {k: next_hard.get(k) for k in ("modality", "stage", "reason", "peak_seconds", "hard_level", "peak_level", "note", "modality_note")},
        "schedule": tp.schedule_for(plan),
        "pages": [{"session_type": st, "label": (plan.get("sessions", {}).get(st) or {}).get("label", st),
                   "page": (plan.get("sessions", {}).get(st) or {}).get("page"),
                   "duration_min": (plan.get("sessions", {}).get(st) or {}).get("duration_min")}
                  for st in tp.active_session_types(plan) if (plan.get("sessions", {}).get(st) or {}).get("page")],
        "next_hard_blocks": next_hard.get("protocol"),
        "sessions": sessions,
        "load_series": load_series,
        "cardio": cardio_hist,
        "progression_rules": plan.get("progression", {}).get("strength", {}),
        "constraints": plan.get("constraints", []),
    }


async def _build_data() -> dict:
    programme = await fit.get_active_programme()
    dash = await fit.compute_dashboard()
    trends = await fit.fetch_trends_series(90)
    bodyfat = await _latest_bodyfat()
    library = {r["slug"]: r for r in await fit.get_all_exercises()}
    await _heal_dead_videos(library)  # check each demo plays; search+heal dead ones, else hide

    w = dash.get("weight", {})
    nut = dash.get("nutrition", {})
    steps = dash.get("steps", {})
    summ = trends.get("summary", {})

    start_w = float(programme["start_weight_kg"]) if programme else None
    target_w = float(programme["target_weight_kg"]) if programme else 75.0
    dur = int(programme["duration_weeks"]) if programme else 18
    week_no = dash.get("week_no", 0) or 0
    days_remaining = dash.get("days_remaining")
    # Current weight independent of programme start so it shows pre-start too.
    _hist = await fit.fetch_weight_history(45)
    _wt = compute_trend(_hist)
    current = _wt.trend_7d or _wt.latest_raw
    latest_raw = _wt.latest_raw  # today's actual scale reading (vs the smoothed trend headline)
    # The kg/wk rate MUST match what the check-in/advisor report, so take it from
    # the programme-start-filtered trend (compute_dashboard), not this unfiltered
    # 45-day line. They used to disagree — e.g. check-in "−1.3/wk" vs hero
    # "+0.3/wk" — because one filtered to programme start and one didn't. Early
    # on, that filtered slope is None (too few days to call a rate); fall back to
    # the unfiltered line only before the programme has started.
    slope = w.get("slope_kg_per_week")
    if slope is None and (not programme or week_no < 1):
        slope = _wt.slope_kg_per_week
    # Date of the most recent raw reading, for the "latest scale" line.
    latest_date = None
    try:
        _r = sorted((x for x in _hist if x.get("value") is not None), key=lambda x: x["date"])
        if _r:
            latest_date = date.fromisoformat(_r[-1]["date"]).strftime("%d %b")
    except Exception:
        latest_date = None
    cum_loss = (start_w - current) if (start_w and current) else None
    prog = (max(0.0, min(100.0, (start_w - current) / (start_w - target_w) * 100))
            if (start_w and current and start_w != target_w) else 0)
    if days_remaining is None and programme:
        end = date.fromisoformat(programme["end_date"])
        days_remaining = max(0, (end - datetime.now(UK_TZ).date()).days)

    # Plan maths — single source of truth (service.compute_plan_maths): the
    # weekly line, gap, required-vs-actual rate and projection. The old inline
    # buckets capped the worst case at "A touch behind" — even 7 kg off the
    # line — which is exactly the softness this replaces.
    eff_week = min(max(week_no, 1), dur)
    plan = fit.compute_plan_maths(programme, current, slope) if programme else None
    if plan:
        target_this_week = plan["target_this_week"]
        on_track_key, on_label = plan["on_track"], plan["on_track_label"]
        # template CSS buckets: warn/neutral/ahead/on track/settling/behind
        css_map = {"pre_start": "warn", "neutral": "neutral", "ahead": "ahead",
                   "on_track": "on track", "settling": "settling",
                   "behind": "behind", "well_behind": "behind", "off_track": "behind"}
        on_track = css_map.get(on_track_key, "neutral")
    else:
        target_this_week = None
        on_track, on_track_key, on_label = "neutral", "neutral", "Tracking"

    hero = {
        "current_weight": _round(current) if current else "—",
        "latest_weight": _round(latest_raw) if latest_raw is not None else "—",
        "latest_date": latest_date or "—",
        "target_weight": _round(target_w),
        "start_weight": _round(start_w) if start_w else "—",
        "progress_pct": _round(prog, 0) or 0,
        "cumulative_loss": _round(cum_loss) if cum_loss is not None else 0,
        "slope": _round(slope) if slope is not None else "—",
        "week_no": week_no, "duration_weeks": dur,
        "days_remaining": days_remaining if days_remaining is not None else "—",
        "target_this_week": target_this_week if target_this_week is not None else "—",
        "on_track": on_track, "on_track_label": on_label,
        "on_track_tier": on_track_key,
        "gap_vs_line_kg": plan.get("gap_vs_line_kg") if plan else None,
        "required_kg_per_week": plan.get("required_kg_per_week") if plan else None,
        "required_rate_unsafe": plan.get("required_rate_unsafe") if plan else False,
        "projected_end_weight": plan.get("projected_end_weight") if plan else None,
        "projected_finish_date": plan.get("projected_finish_date") if plan else None,
        "start_date": programme["start_date"] if programme else None,
        "end_date": programme["end_date"] if programme else None,
    }

    # Resolve the active goal phase — it drives the protein target and all the
    # framing below, so nothing here is hardcoded to a specific number/phase.
    goal = fit.resolve_goal(programme, current) if programme else {
        "phase": {}, "effective_phase": "default", "current_phase": "default",
    }
    phase = goal.get("phase") or {}
    protein_spec = phase.get("protein") or {}

    tgt_cal = nut.get("target_calories") or (programme["daily_calorie_target"] if programme else 2050)
    # No-programme fallback (120) mirrors the nutrition domain's documented
    # default; the live value comes from nut["target_protein"] in practice.
    tgt_pro = nut.get("target_protein") or (programme["daily_protein_g"] if programme else 120)

    def sleep_status(v):
        return "neutral" if v is None else "good" if v >= 70 else "watch" if v >= 50 else "bad"

    sc = (summ.get("sleep_score") or {}).get("current")
    hrv = (summ.get("hrv") or {}).get("current")
    rhr = (summ.get("resting_hr") or {}).get("current")
    stress = (summ.get("stress") or {}).get("current")

    metrics = [
        {"label": "Weight", "value": f"{hero['current_weight']} kg",
         "sub": f"target {hero['target_this_week']} kg this week", "status": on_track if on_track in ("good", "watch", "bad") else ("good" if on_track in ("on track", "ahead") else "watch")},
        {"label": "Body fat", "value": (f"{bodyfat['pct']}%" if bodyfat else "—"),
         "sub": (f"as of {bodyfat['date']} · goal 15%" if bodyfat else "re-weigh on Body scale"),
         "status": "neutral"},
        {"label": "Protein today", "value": f"{int(nut.get('protein_g') or 0)} / {tgt_pro} g",
         "sub": ("protein floor" if protein_spec.get("mode") == "fixed" else "lean-mass fuel"),
         "status": "good" if (nut.get('protein_g') or 0) >= tgt_pro * 0.95 else "watch"},
        {"label": "Calories today", "value": f"{int(nut.get('calories') or 0)} / {tgt_cal}",
         "sub": "deficit auto-eases as you lean out", "status": "good" if (nut.get('calories') or 0) <= tgt_cal * 1.05 else "watch"},
        {"label": "Steps", "value": f"{int(steps.get('today') or 0):,}",
         "sub": f"7-day avg {int(steps.get('avg_7d') or 0):,} · aim {(int(programme['daily_steps_target'])//1000) if programme else 15}k", "status": "good" if (steps.get('avg_7d') or 0) >= 10000 else "watch"},
        {"label": "Sleep score", "value": (f"{sc:.0f}" if sc else "—"),
         "sub": "14-day avg", "status": sleep_status(sc)},
        {"label": "HRV", "value": (f"{hrv:.0f} ms" if hrv else "—"),
         "sub": "recovery · higher = better", "status": _status_from_delta((summ.get('hrv') or {}).get('delta_pct'), good_up=True)},
        {"label": "Resting HR", "value": (f"{rhr:.0f} bpm" if rhr else "—"),
         "sub": "lower = fitter", "status": _status_from_delta((summ.get('resting_hr') or {}).get('delta_pct'), good_up=False)},
        {"label": "Stress", "value": (f"{stress:.0f}" if stress else "—"),
         "sub": "14-day avg · lower = calmer", "status": _status_from_delta((summ.get('stress') or {}).get('delta_pct'), good_up=False)},
    ]

    # weekly plan
    split = programme["split"] if programme else "4x_upper_lower"
    try:
        if programme:
            sessions = {s.day_of_week: session_to_dict(s) for s in await fit.week_sessions_for(programme, eff_week)}
        else:
            sessions = {s.day_of_week: session_to_dict(s) for s in generate_week(split, eff_week)}
    except Exception as e:
        logger.warning(f"Dashboard: week generation failed: {e}")
        sessions = {}
    today_index = datetime.now(UK_TZ).weekday()
    days, used_slugs = [], {}
    for dow in range(7):
        s = sessions.get(dow)
        if not s:
            days.append({"name": DAY_NAMES[dow], "label": "Rest", "short": "Rest", "type": "rest",
                         "is_rest": True, "note": "", "exercises": []})
            continue
        exs = []
        for e in s.get("exercises", []):
            lib = library.get(e["exercise_slug"], {})
            detail = (f"{e['sets']} × {e['reps']}" if e.get("reps")
                      else f"{e['sets']} × {e['hold_s']}s" if e.get("hold_s") else f"{e['sets']} sets")
            vid = _yt_id(lib.get("video_url"))
            name = lib.get("name", e["exercise_slug"])
            if vid:
                used_slugs[e["exercise_slug"]] = {"name": name, "group": lib.get("muscle_group", ""),
                                                  "cue": lib.get("form_cue"), "video_id": vid}
            exs.append({"name": name, "detail": detail, "cue": lib.get("form_cue"), "video_id": vid})
        short = s["label"].split("(")[0].strip()
        days.append({"name": DAY_NAMES[dow], "label": s["label"],
                     "short": ("Rest" if s.get("is_rest") else short),
                     "type": s.get("session_type"), "is_rest": bool(s.get("is_rest")),
                     "note": s.get("notes") or "", "exercises": exs})

    training = await _training_payload(programme, library)
    plan_driven = training is not None
    strength_n = int(programme["weekly_strength_sessions"]) if programme else 4
    steps_aim_k = (int(programme["daily_steps_target"]) // 1000) if programme else 15
    if protein_spec.get("mode") == "fixed":
        protein_target_str = f"{tgt_pro} g"
    else:
        _gpk = protein_spec.get("g_per_kg")
        protein_target_str = f"~{_gpk:g} g/kg (~{tgt_pro} g)" if _gpk else f"{tgt_pro} g"

    rationale = {
        "targets": [
            ["Calories", f"~{int(tgt_cal):,} kcal"], ["Protein", protein_target_str],
            ["Water", "3 L (3.5 L training days)"], ["Steps", f"{steps_aim_k}k/day"],
            ["Strength", f"{strength_n} × 40–45 min gym / week (Mon · Tue · Thu · Sat)" if plan_driven else f"{strength_n} × 30 min / week"],
            *([["Cardio", "1 hard (Wed — stairmaster pyramid or equivalent) + easy Fri 30–40 min; optional 10–20 min after lifts; 8–10k steps counts"]] if plan_driven else []),
            ["Mobility", "10 min daily"],
            ["Sleep", "8h · 22:30–06:30"],
        ],
        "paras": [
            f"Current goal: reach {hero['target_weight']} kg. " + (phase.get("focus") or ""),
            phase.get("protein_note") or "",
            f"Calories are ~{int(tgt_cal):,} now and auto-ease as you lose weight (the deficit stays honest "
            "as BMR drops). Steps are the accelerator, not the foundation: a sedentary day still loses fat, "
            "an active one loses more — so a low-step day is never a failure.",
            ("Training is a standing week from 7 Sep: Upper A push (Mon), Lower A (Tue), Upper B pull (Thu) and a light "
             "full body (Sat) on machines and dumbbells with double progression: every set at target with two reps in "
             "reserve earns one plate; a failed set holds; two failed sessions deload. The weaker (left) side leads on "
             "single-arm / single-leg work and the stronger side matches its reps. Cardio is one hard session a week "
             "(Wed — the stairmaster pyramid is the example, any hard modality is interchangeable) plus easy cardio on "
             "Friday, optional short easy cardio after lifts, and 8–10k-step days count. No second hard session before "
             "week 6. Hip rule: sharp or pinching pain means stop and switch to the bike. Breakfast and lunch are locked "
             "for simplicity; dinner flexes with the family."
             if plan_driven else
             "Training is bodyweight + bands + light (<5 kg) loads, hip- and sciatica-friendly (no running, no loaded "
             "spinal flexion). Breakfast and lunch are locked for simplicity; dinner flexes with the family."),
        ],
        "rules": [
            phase.get("rule") or f"Hit ~{tgt_pro} g protein.",
            "Log everything (the coach tracks it).",
            (f"Lift {strength_n}× on the fixed days (Mon · Tue · Thu · Sat), 1 hard cardio (Wed), easy cardio Fri, 10-min hip mobility every day."
             if plan_driven else f"Walk daily, lift {strength_n}×, 10-min hip mobility every day."),
            "Bed 22:30, caffeine before noon, last food ≥2h before bed.",
            "Weigh in each Monday on the Withings Body scale — that's your checkpoint.",
        ],
        "disclaimer": "Coming off sertraline should stay GP-supervised, and taper symptoms can overlap with diet/training "
                      "changes — keep your GP in the loop and book a physio screen for the hip/sciatica. This is support, "
                      "not medical advice.",
    }

    try:
        completed_days = await _completed_days_nutrition(7)
    except Exception as e:
        logger.warning(f"Dashboard: completed-days nutrition fetch failed: {e}")
        completed_days = None

    facts = {"hero": hero, "plan": plan,
             "metrics": [{k: m[k] for k in ("label", "value", "sub", "status")} for m in metrics],
             "nutrition_completed_days": completed_days,
             "trends_summary": summ,
             "goal": {"phase": goal.get("effective_phase"), "label": phase.get("label"),
                      "focus": phase.get("focus"), "protein_target": tgt_pro,
                      "protein_note": phase.get("protein_note")}}
    summary = await _ai_summary(facts)

    return {
        "generated_at": datetime.now(UK_TZ).strftime("%a %d %b %Y, %H:%M"),
        "hero": hero, "metrics": metrics, "summary": summary,
        "trends": trends,
        "plan": {"today_index": today_index, "days": days},
        "mobility": _mobility_rotation(library, today_index),
        "exercises": list(used_slugs.values()),
        "rationale": rationale,
        "training": training,
    }


# ── encrypt + render + deploy ──────────────────────────────────────────

def _encrypt(obj: dict, passcode: str) -> dict:
    salt = os.urandom(16)
    iv = os.urandom(12)
    key = hashlib.pbkdf2_hmac("sha256", passcode.encode(), salt, PBKDF2_ITERS, dklen=32)
    ct = AESGCM(key).encrypt(iv, json.dumps(obj, default=str).encode(), None)
    b = lambda x: base64.b64encode(x).decode()
    return {"payload": b(ct), "salt": b(salt), "iv": b(iv)}


def _inject(payload="", salt="", iv="", plain="null", generated_at="") -> str:
    html = TEMPLATE.read_text(encoding="utf-8")
    return (html
            .replace("__PAYLOAD__", payload)
            .replace("__SALT__", salt)
            .replace("__IV__", iv)
            .replace("__ITERS__", str(PBKDF2_ITERS))
            .replace("__PLAIN_DATA__", plain)
            .replace("__GENERATED_AT__", generated_at))


def _render(enc: dict, generated_at: str) -> str:
    """Encrypted build for the public surge URL (passcode gate)."""
    return _inject(payload=enc["payload"], salt=enc["salt"], iv=enc["iv"],
                   plain="null", generated_at=generated_at)


def _render_plain(data: dict, generated_at: str) -> str:
    """Plaintext build for the LAN-served page (no WebCrypto / no gate)."""
    blob = json.dumps(data, default=str).replace("</", "<\\/")  # avoid </script> break-out
    return _inject(plain=blob, generated_at=generated_at)


def _resolve_surge() -> str:
    """Locate the surge CLI. NSSM services can launch with a PATH that omits the
    global npm bin dir (this is why the scheduled DiscordBot build deploys but a
    HadleyAPI-triggered refresh silently fails to push to surge), so fall back to
    the known npm install location under the user profile."""
    for name in ("surge", "surge.cmd"):
        found = shutil.which(name)
        if found:
            return found
    if os.name == "nt":
        for base in (os.environ.get("APPDATA", ""), os.path.expanduser("~/AppData/Roaming")):
            if not base:
                continue
            cand = Path(base) / "npm" / "surge.cmd"
            if cand.exists():
                return str(cand)
    return "surge"


def _deploy(html: str, domain: str, extra_files: dict[str, str] | None = None) -> bool:
    d = Path(tempfile.mkdtemp(prefix="reset-cut-"))
    (d / "index.html").write_text(html, encoding="utf-8")
    (d / "200.html").write_text(html, encoding="utf-8")  # SPA fallback
    for fn, body in (extra_files or {}).items():         # session pages (upper-a.html …)
        (d / fn).write_text(body, encoding="utf-8")
    env = dict(os.environ)
    # SURGE_LOGIN/SURGE_TOKEN in .env make this non-interactive.
    # On Windows surge is surge.cmd — invoke via cmd /c so PATH resolution +
    # spaces in the temp path are handled correctly (shell=False keeps args
    # individually quoted).
    surge_bin = _resolve_surge()
    if os.name == "nt":
        cmd = ["cmd", "/c", surge_bin, str(d), domain]
    else:
        cmd = [surge_bin, str(d), domain]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180, env=env,
            encoding="utf-8", errors="replace",  # surge prints unicode; avoid cp1252 crash
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        ok = "Success" in out or "Published" in out or proc.returncode == 0
        if not ok:
            logger.error(f"Surge deploy failed: {out[-400:]}")
        else:
            logger.info(f"Surge deploy ok: {domain}")
        return ok
    except Exception as e:
        logger.error(f"Surge deploy error: {e}")
        return False


async def build_and_deploy(deploy: bool = True) -> dict:
    passcode = os.getenv("DASHBOARD_PASSCODE", "")
    domain = os.getenv("DASHBOARD_DOMAIN", "chris-reset-cut.surge.sh")
    if not passcode:
        raise RuntimeError("DASHBOARD_PASSCODE not set")
    data = await _build_data()
    enc_html = _render(_encrypt(data, passcode), data["generated_at"])   # public surge (gated)
    plain_html = _render_plain(data, data["generated_at"])               # LAN page (no gate)
    result = {"domain": domain, "url": f"https://{domain}", "bytes": len(enc_html),
              "generated_at": data["generated_at"], "deployed": False}
    # The LAN endpoint (GET /fitness/dashboard/page) serves this plaintext file —
    # works on any home-network device without WebCrypto, and the refresh works there.
    LOCAL_HTML.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_HTML.write_text(plain_html, encoding="utf-8")
    result["local"] = str(LOCAL_HTML)
    # Session pages (Upper A / Lower A / Upper B / Full body) with the API's
    # next-session targets baked in; deployed next to index.html and mirrored
    # locally for GET /fitness/session-pages/<name>.
    pages = await _session_pages(data["generated_at"])
    LOCAL_PAGES_DIR.mkdir(parents=True, exist_ok=True)
    for fn, body in pages.items():
        (LOCAL_PAGES_DIR / fn).write_text(body, encoding="utf-8")
    result["session_pages"] = sorted(pages)
    if deploy:
        result["deployed"] = _deploy(enc_html, domain, pages)
    return result


async def _session_pages(generated_at: str) -> dict[str, str]:
    """Render every session page with that session's next-session targets.
    A target lookup failure degrades to the page's static suggestions — the
    dashboard build must never fail because of a page."""
    from domains.fitness import session_pages as sp
    targets: dict[str, dict] = {}
    for name, session_type in sp.PAGE_SESSIONS.items():
        try:
            bundle = await fit.next_session_bundle(session_type)
            targets[name] = sp.page_targets(bundle, generated_at)
        except Exception as e:
            logger.warning(f"Dashboard: session-page targets failed for {name}: {e}")
    try:
        return sp.build_pages(targets)
    except Exception as e:
        logger.error(f"Dashboard: session pages not built: {e}")
        return {}


if __name__ == "__main__":
    import asyncio
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    res = asyncio.run(build_and_deploy(deploy=True))
    print(json.dumps(res, indent=2))
