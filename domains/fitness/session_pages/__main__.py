"""CLI: python -m domains.fitness.session_pages [--sync | --check | <out_dir>]"""
import sys
from pathlib import Path

from domains.fitness.session_pages import HERE, PAGE_SESSIONS, build_pages, sync_runtime

if "--sync" in sys.argv:
    print("synced:", sync_runtime(write=True) or "nothing to do")
elif "--check" in sys.argv:
    stale = sync_runtime(write=False)
    print("stale:", stale or "none")
    sys.exit(1 if stale else 0)
else:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "_build"
    out.mkdir(parents=True, exist_ok=True)
    for fn, html in build_pages().items():
        (out / fn).write_text(html, encoding="utf-8")
    print("built", sorted(PAGE_SESSIONS), "->", out)
