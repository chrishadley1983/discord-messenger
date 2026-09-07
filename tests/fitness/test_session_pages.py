"""Session pages: committed pages carry the current runtime, targets inject cleanly,
and every exercise on a page maps to a slug in that session's plan entry."""
import re

import pytest

from domains.fitness import session_pages as sp
from domains.fitness import training_plan as tp


def _page_slugs(html: str) -> list[str]:
    i = html.index("const ex = [")
    j = html.index("];", i)
    return re.findall(r'"?slug"?:\s*"([a-z0-9-]+)"', html[i:j])


class TestCommittedPages:
    @pytest.mark.parametrize("name", sorted(sp.PAGE_SESSIONS))
    def test_page_exists_with_markers(self, name):
        html = sp.page_path(name).read_text(encoding="utf-8")
        for marker in (sp.RUNTIME_START, sp.RUNTIME_END, sp.TARGETS_START, sp.TARGETS_END):
            assert marker in html, f"{name}: missing {marker}"
        assert f'data-page="{name}"' in html and f'data-session="{sp.PAGE_SESSIONS[name]}"' in html
        assert 'id="reset"' in html and 'id="playBtn"' in html and 'id="targetsAt"' in html
        # single-file: no external scripts/styles other than Google Fonts
        ext = re.findall(r'<(?:script|link)[^>]+(?:src|href)="(https?://[^"]+)"', html)
        assert all("fonts.googleapis.com" in u for u in ext), ext

    def test_committed_pages_carry_the_current_runtime(self):
        # `python -m domains.fitness.session_pages --sync` fixes this
        assert sp.sync_runtime(write=False) == []

    @pytest.mark.parametrize("name", sorted(sp.PAGE_SESSIONS))
    def test_page_exercises_match_the_plan(self, name):
        html = sp.page_path(name).read_text(encoding="utf-8")
        plan_slugs = [e["slug"] for e in tp.default_plan()["sessions"][sp.PAGE_SESSIONS[name]]["exercises"]]
        assert _page_slugs(html) == plan_slugs

    def test_runtime_rules(self):
        js = sp.runtime_source()
        # S1: reset clears ticks only — it must not touch kg / the kg store
        reset = re.search(r'\$\("reset"\)\.onclick\s*=\s*\(\)\s*=>\s*\{(.*?)\};', js, re.S).group(1)
        assert "ticks.fill(false)" in reset and "kg" not in reset and "KEY_KG" not in reset
        # S3: ticks restored only for today's date
        assert "storedTicks.date === todayKey()" in js
        # S4: play mode still opens at the first incomplete exercise
        assert 'cur = ex.findIndex((e, i) => !state[i].ticks.every(Boolean))' in js
        # S2: entered kg persists per exercise
        assert "persistKg()" in js and 'KEY_KG = "rc:" + PAGE + ":kg"' in js


class TestTargets:
    def test_page_targets_shape(self):
        bundle = {"session_type": "upper_a", "known": True, "plan_version": 6, "exercises": [
            {"slug": "db-flat-bench-press", "sets": 3, "target_reps": 10, "action": "increase", "weight_kg": 14.0,
             "last_weight_kg": 12.0, "reason": "go up", "last": {"top_weight": 12.0}},
            {"slug": "shoulder-press", "sets": 3, "target_reps": 10, "action": "hold", "weight_kg": 25.0,
             "reason": "hold", "last": {"top_weight": 25.0}},
        ]}
        t = sp.page_targets(bundle, "2026-09-07 20:00")
        assert t["session_type"] == "upper_a" and t["generated_at"] == "2026-09-07 20:00"
        assert t["exercises"]["db-flat-bench-press"] == {"action": "increase", "weight_kg": 14.0, "last_kg": 12.0,
                                                          "reason": "go up", "sets": 3, "target_reps": 10}
        assert t["exercises"]["shoulder-press"]["last_kg"] == 25.0
        assert sp.page_targets({"known": False}) == {} and sp.page_targets(None) == {}

    def test_render_injects_targets_and_escapes_script_close(self):
        html = sp.render_page("upper-b", {"exercises": {"lat-pulldown": {"reason": "</script><b>x"}}})
        assert 'const TARGETS = {"exercises": {"lat-pulldown": {"reason": "<\\/script><b>x"}}};' in html
        assert html.count("<script") == html.count("</script>")

    def test_build_pages_all_four(self):
        out = sp.build_pages({"upper-a": {"exercises": {}}})
        assert sorted(out) == ["full-body.html", "lower-a.html", "upper-a.html", "upper-b.html"]
        assert "const TARGETS = {};" in out["lower-a.html"]
