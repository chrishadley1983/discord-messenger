"""Reset Cut session pages — the phone-facing workout pages (Upper A / Lower A /
Upper B / Full body) that deploy alongside the surge dashboard.

Each page in ``pages/`` is a committed, standalone single-file HTML (Google
Fonts only, illustrations embedded as base64). Two marked blocks inside each
page are owned by this module:

* ``/*RUNTIME-START*/ … /*RUNTIME-END*/`` — the shared JS runtime, whose single
  source is ``runtime.js`` (persistence, per-session reset, play mode).
  ``sync_runtime()`` writes it back into the committed pages so they stay
  standalone; ``test_session_pages`` fails if a page drifts.
* ``/*TARGETS-START*/ … /*TARGETS-END*/`` — ``const TARGETS = {...}``: the
  API's next-session targets for that page's session type, injected at
  build/deploy time by ``build_pages``. Committed pages carry ``{}``.

The page reads: entered kg (localStorage) > TARGETS (API) > static suggestion.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGES_DIR = HERE / "pages"
RUNTIME_JS = HERE / "runtime.js"

RUNTIME_START, RUNTIME_END = "/*RUNTIME-START*/", "/*RUNTIME-END*/"
TARGETS_START, TARGETS_END = "/*TARGETS-START*/", "/*TARGETS-END*/"

# page file stem -> plan session_type
PAGE_SESSIONS: dict[str, str] = {
    "upper-a": "upper_a",
    "lower-a": "lower_a",
    "upper-b": "upper_b",
    "full-body": "full_body",
}

_RUNTIME_RE = re.compile(re.escape(RUNTIME_START) + r".*?" + re.escape(RUNTIME_END), re.S)
_TARGETS_RE = re.compile(re.escape(TARGETS_START) + r".*?" + re.escape(TARGETS_END), re.S)


def page_path(name: str) -> Path:
    if name not in PAGE_SESSIONS:
        raise KeyError(f"unknown session page {name!r}; known: {sorted(PAGE_SESSIONS)}")
    return PAGES_DIR / f"{name}.html"


def runtime_source() -> str:
    return RUNTIME_JS.read_text(encoding="utf-8")


def _runtime_block() -> str:
    return f"{RUNTIME_START}\n{runtime_source().rstrip()}\n{RUNTIME_END}"


def _targets_block(targets: dict | None) -> str:
    blob = json.dumps(targets or {}, default=str, ensure_ascii=False).replace("</", "<\\/")
    return f"{TARGETS_START}\nconst TARGETS = {blob};\n{TARGETS_END}"


def page_targets(next_session: dict | None, generated_at: str | None = None) -> dict:
    """Shape a ``GET /fitness/next-session`` bundle into what the page runtime reads."""
    if not next_session or not next_session.get("known", True):
        return {}
    exs = {}
    for e in next_session.get("exercises") or []:
        last = e.get("last") or {}
        exs[e["slug"]] = {
            "action": e.get("action"),
            "weight_kg": e.get("weight_kg"),
            "last_kg": e.get("last_weight_kg", last.get("top_weight")),
            "reason": e.get("reason"),
            "sets": e.get("sets"),
            "target_reps": e.get("target_reps"),
        }
    return {
        "session_type": next_session.get("session_type"),
        "plan_version": next_session.get("plan_version"),
        "generated_at": generated_at,
        "exercises": exs,
    }


def render_page(name: str, targets: dict | None = None) -> str:
    """The committed page with the current runtime.js and the given targets injected."""
    html = page_path(name).read_text(encoding="utf-8")
    if not _RUNTIME_RE.search(html) or not _TARGETS_RE.search(html):
        raise ValueError(f"{name}.html is missing the RUNTIME/TARGETS markers")
    html = _RUNTIME_RE.sub(lambda _m: _runtime_block(), html)
    html = _TARGETS_RE.sub(lambda _m: _targets_block(targets), html)
    return html


def build_pages(targets_by_page: dict[str, dict] | None = None) -> dict[str, str]:
    """{filename: html} for every page, ready to drop into the deploy directory."""
    targets_by_page = targets_by_page or {}
    return {f"{name}.html": render_page(name, targets_by_page.get(name)) for name in PAGE_SESSIONS}


def sync_runtime(write: bool = True) -> list[str]:
    """Re-embed runtime.js (and an empty TARGETS block) into the committed pages.
    Returns the names of pages that were out of date."""
    stale = []
    for name in PAGE_SESSIONS:
        p = page_path(name)
        before = p.read_text(encoding="utf-8")
        after = render_page(name, {})
        if before != after:
            stale.append(name)
            if write:
                p.write_text(after, encoding="utf-8")
    return stale
