"""Generator for Chris's reset-cut dashboard.

Static, passcode-encrypted (AES-GCM), surge-hosted single page. Pulls live data
from the fitness service + Withings body comp, asks the local AI coach (Pete) for
an expert summary via the jobs-channel, encrypts the whole payload with the
DASHBOARD_PASSCODE, injects it into the template and deploys to surge.

Rebuilt daily (see bot.py) so the static snapshot stays current.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
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
    prompt = (
        "You are Pete, Chris's expert personal trainer and nutrition coach. "
        "Write a concise expert summary (4–6 sentences, plain text, NO markdown headings) "
        "of his reset cut using the data below. Cover: progress vs the 75kg/15% target and "
        "this week's trend-weight line; what's going well; the ONE thing to focus on this week; "
        "and a calm, encouraging close. He is tapering sertraline (GP-supervised) so keep the "
        "tone supportive, never guilt-trippy; frame walking as stress relief. Be specific with his "
        "numbers. When done, call the reply tool with the job_id and your summary text only.\n\n"
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
    # Fallback — deterministic, still useful
    h = facts.get("hero", {})
    return (
        f"You're {h.get('current_weight','?')}kg, down {h.get('cumulative_loss','?')}kg toward 75kg "
        f"({h.get('progress_pct','?')}% there) with {h.get('days_remaining','?')} days to go. "
        "Trend is the only number that matters week to week — keep protein at 180g to protect muscle, "
        "and treat the daily walk as much for your head as your waistline. Lock breakfast and lunch, "
        "let dinner flex with the family, and keep showing up. Steady wins this."
    )


# ── data assembly ──────────────────────────────────────────────────────

async def _build_data() -> dict:
    programme = await fit.get_active_programme()
    dash = await fit.compute_dashboard()
    trends = await fit.fetch_trends_series(90)
    bodyfat = await _latest_bodyfat()
    library = {r["slug"]: r for r in await fit.get_all_exercises()}

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
    _wt = compute_trend(await fit.fetch_weight_history(45))
    current = _wt.trend_7d or _wt.latest_raw
    slope = _wt.slope_kg_per_week
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
    else:
        on_track, on_label = "behind", "Behind — tighten up"

    hero = {
        "current_weight": _round(current) if current else "—",
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

    tgt_cal = nut.get("target_calories") or (programme["daily_calorie_target"] if programme else 2050)
    tgt_pro = nut.get("target_protein") or (programme["daily_protein_g"] if programme else 180)

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
         "sub": "lean-mass insurance", "status": "good" if (nut.get('protein_g') or 0) >= tgt_pro * 0.95 else "watch"},
        {"label": "Calories today", "value": f"{int(nut.get('calories') or 0)} / {tgt_cal}",
         "sub": "deficit auto-eases as you lean out", "status": "good" if (nut.get('calories') or 0) <= tgt_cal * 1.05 else "watch"},
        {"label": "Steps", "value": f"{int(steps.get('today') or 0):,}",
         "sub": f"7-day avg {int(steps.get('avg_7d') or 0):,} · aim 15k", "status": "good" if (steps.get('avg_7d') or 0) >= 10000 else "watch"},
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

    rationale = {
        "targets": [
            ["Calories", "~2,050 kcal"], ["Protein", "180 g"],
            ["Water", "3 L (3.5 L training days)"], ["Steps", "15k aim · 10k floor"],
            ["Strength", "4 × 30 min / week"], ["Mobility", "10 min daily"],
            ["Sleep", "8h · 22:30–06:30"],
        ],
        "paras": [
            "Goal: 75 kg and ~15% body fat by 23 October — about 0.8 kg/week, the upper edge of a safe rate. "
            "75 kg is very achievable; 15% is the stretch, so the plan optimises toward it with high protein and strength.",
            "The two targets only line up if lean mass is protected — that's why protein (180g, ~2 g/kg) and lifting "
            "4× a week are non-negotiable, not optional extras. Without them you'd end up light but soft.",
            "Calories are ~2,050 now and auto-ease as you lose weight (the deficit stays honest as BMR drops). "
            "Steps are the accelerator, not the foundation: a sedentary day still loses ~0.5 kg/wk, an active one ~0.9 — "
            "so a low-step day is never a failure.",
            "Training is bodyweight + bands + light (<5 kg) loads, hip- and sciatica-friendly (no running, no loaded "
            "spinal flexion). Breakfast and lunch are locked for simplicity; dinner flexes with the family.",
        ],
        "rules": [
            "Hit 180g protein — it protects muscle. Non-negotiable.",
            "Log everything (the coach tracks it).",
            "Walk daily, lift 4×, 10-min hip mobility every day.",
            "Bed 22:30, caffeine before noon, last food ≥2h before bed.",
            "Weigh in each Monday on the Withings Body scale — that's your checkpoint.",
        ],
        "disclaimer": "Coming off sertraline should stay GP-supervised, and taper symptoms can overlap with diet/training "
                      "changes — keep your GP in the loop and book a physio screen for the hip/sciatica. This is support, "
                      "not medical advice.",
    }

    facts = {"hero": hero, "metrics": [{k: m[k] for k in ("label", "value", "sub", "status")} for m in metrics],
             "trends_summary": summ}
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


def _deploy(html: str, domain: str) -> bool:
    d = Path(tempfile.mkdtemp(prefix="reset-cut-"))
    (d / "index.html").write_text(html, encoding="utf-8")
    (d / "200.html").write_text(html, encoding="utf-8")  # SPA fallback
    env = dict(os.environ)
    # SURGE_LOGIN/SURGE_TOKEN in .env make this non-interactive.
    # On Windows surge is surge.cmd — invoke via cmd /c so PATH resolution +
    # spaces in the temp path are handled correctly (shell=False keeps args
    # individually quoted).
    if os.name == "nt":
        cmd = ["cmd", "/c", "surge", str(d), domain]
    else:
        cmd = ["surge", str(d), domain]
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
