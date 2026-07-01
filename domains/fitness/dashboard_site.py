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

async def _ai_summary(facts: dict) -> str:
    g = facts.get("goal", {})
    prompt = (
        "You are Pete, Chris's expert personal trainer and nutrition coach. "
        "Write a concise expert summary (4–6 sentences, plain text, NO markdown headings) "
        "of his cut using the data below. Frame everything around his CURRENT goal/phase "
        f"(\"{g.get('label','')}\": {g.get('focus','')}). Cover: progress vs his target weight and "
        "this week's trend-weight line; what's going well; the ONE thing to focus on this week; "
        "and a calm, encouraging close. He is tapering sertraline (GP-supervised) so keep the "
        "tone supportive, never guilt-trippy; frame walking as stress relief. Be specific with his "
        "numbers and use the protein target from the data — never invent a different one. When "
        "done, call the reply tool with the job_id and your summary text only.\n\n"
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
    # Fallback — deterministic, still useful. Protein line comes from the goal
    # phase (its protein_note), so it tracks the current target, never 180g.
    h = facts.get("hero", {})
    protein_line = g.get("protein_note") or (
        f"hold protein around {g.get('protein_target','?')}g"
    )
    return (
        f"You're {h.get('current_weight','?')}kg, down {h.get('cumulative_loss','?')}kg toward "
        f"{h.get('target_weight','?')}kg ({h.get('progress_pct','?')}% there) with "
        f"{h.get('days_remaining','?')} days to go. Trend is the only number that matters week to "
        f"week — {protein_line}, and treat the daily walk as much for your head as your waistline. "
        "Lock breakfast and lunch, let dinner flex with the family, and keep showing up. Steady wins this."
    )


# ── data assembly ──────────────────────────────────────────────────────

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

    # trajectory line for "this week"
    eff_week = min(max(week_no, 1), dur)
    target_this_week = None
    if start_w is not None:
        target_this_week = _round(start_w - (start_w - target_w) * (eff_week / dur), 1)

    if week_no < 1:
        on_track, on_label = "warn", "Starts Monday"
    elif current is None or target_this_week is None:
        on_track, on_label = "neutral", "Tracking"
    elif current <= target_this_week - 0.2:
        on_track, on_label = "ahead", "Ahead of plan"
    elif current <= target_this_week + 0.3:
        on_track, on_label = "on track", "On track"
    elif week_no <= 2:
        # Early programme: weight noise dwarfs a 0.3 kg miss off a micro-target.
        # Don't flag "behind" and don't guilt-trip while the baseline settles.
        on_track, on_label = "settling", "Settling in"
    else:
        on_track, on_label = "behind", "A touch behind"

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
            ["Strength", f"{strength_n} × 30 min / week"], ["Mobility", "10 min daily"],
            ["Sleep", "8h · 22:30–06:30"],
        ],
        "paras": [
            f"Current goal: reach {hero['target_weight']} kg. " + (phase.get("focus") or ""),
            phase.get("protein_note") or "",
            f"Calories are ~{int(tgt_cal):,} now and auto-ease as you lose weight (the deficit stays honest "
            "as BMR drops). Steps are the accelerator, not the foundation: a sedentary day still loses fat, "
            "an active one loses more — so a low-step day is never a failure.",
            "Training is bodyweight + bands + light (<5 kg) loads, hip- and sciatica-friendly (no running, no loaded "
            "spinal flexion). Breakfast and lunch are locked for simplicity; dinner flexes with the family.",
        ],
        "rules": [
            phase.get("rule") or f"Hit ~{tgt_pro} g protein.",
            "Log everything (the coach tracks it).",
            f"Walk daily, lift {strength_n}×, 10-min hip mobility every day.",
            "Bed 22:30, caffeine before noon, last food ≥2h before bed.",
            "Weigh in each Monday on the Withings Body scale — that's your checkpoint.",
        ],
        "disclaimer": "Coming off sertraline should stay GP-supervised, and taper symptoms can overlap with diet/training "
                      "changes — keep your GP in the loop and book a physio screen for the hip/sciatica. This is support, "
                      "not medical advice.",
    }

    facts = {"hero": hero, "metrics": [{k: m[k] for k in ("label", "value", "sub", "status")} for m in metrics],
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


def _deploy(html: str, domain: str) -> bool:
    d = Path(tempfile.mkdtemp(prefix="reset-cut-"))
    (d / "index.html").write_text(html, encoding="utf-8")
    (d / "200.html").write_text(html, encoding="utf-8")  # SPA fallback
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
    if deploy:
        result["deployed"] = _deploy(enc_html, domain)
    return result


if __name__ == "__main__":
    import asyncio
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    res = asyncio.run(build_and_deploy(deploy=True))
    print(json.dumps(res, indent=2))
