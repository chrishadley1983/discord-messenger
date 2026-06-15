"""Self-contained Audible bridge — runs INSIDE the audible-mcp uv env.

The `audible` pip package pins httpx in ways that conflict with the
anthropic/supabase stack, so it must never be installed into the shared
Pythons (it broke DiscordBot startup on 2026-06-10). Instead client.py
shells out to this script via `uv run --directory <audible-mcp>`, whose
lockfile resolves audible + httpx 0.28 cleanly.

Usage: python _bridge.py <command> '<json-args>'   → JSON on stdout
Commands: library | finished | similar | search | stats
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

AUTH_FILE = Path(__file__).resolve()  # placeholder; replaced below

LIBRARY_RESPONSE_GROUPS = ",".join([
    "product_details", "product_attrs", "contributors", "media", "rating",
    "series", "is_finished", "listening_status", "product_desc",
])
CATALOGUE_RESPONSE_GROUPS = ",".join([
    "contributors", "media", "product_attrs", "product_desc", "rating",
    "sample", "series", "category_ladders",
])


def _client(auth_file: str):
    import audible

    auth = audible.Authenticator.from_file(auth_file)
    return audible.Client(auth=auth)


def summarise(item: dict) -> dict:
    runtime_min = item.get("runtime_length_min") or 0
    overall = (item.get("rating") or {}).get("overall_distribution") or {}
    return {
        "asin": item.get("asin"),
        "title": item.get("title"),
        "subtitle": item.get("subtitle"),
        "authors": [a.get("name") for a in item.get("authors") or []],
        "narrators": [n.get("name") for n in item.get("narrators") or []],
        "series": [
            {"name": s.get("title"), "position": s.get("sequence")}
            for s in item.get("series") or []
        ],
        "runtime_hours": round(runtime_min / 60, 1) if runtime_min else 0,
        "purchase_date": str(item.get("purchase_date") or "") or None,
        "release_date": str(item.get("release_date") or "") or None,
        "percent_complete": item.get("percent_complete", 0),
        "is_finished": item.get("is_finished", False),
        "average_rating": overall.get("display_average_rating"),
        "my_rating": overall.get("display_stars"),
        "publisher_summary": item.get("publisher_summary"),
    }


def cmd_library(client, args):
    lib = client.get(
        "library",
        num_results=max(1, min(int(args.get("num_results", 1000)), 1000)),
        sort_by="-PurchaseDate",
        response_groups=LIBRARY_RESPONSE_GROUPS,
        image_sizes="500",
    )
    return [summarise(i) for i in lib.get("items", [])]


def cmd_finished(client, args):
    books = cmd_library(client, {"num_results": 1000})
    cutoff = None
    if args.get("since"):
        cutoff = datetime.fromisoformat(str(args["since"]).replace("Z", "+00:00"))
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)
    out = []
    for b in books:
        if not b["is_finished"]:
            continue
        if cutoff is not None:
            if not b.get("purchase_date"):
                continue
            try:
                p = datetime.fromisoformat(str(b["purchase_date"]).replace("Z", "+00:00"))
                if p.tzinfo is None:
                    p = p.replace(tzinfo=timezone.utc)
                if p < cutoff:
                    continue
            except ValueError:
                continue
        out.append(b)
    return out


def cmd_similar(client, args):
    sims = client.get(
        f"catalog/products/{args['asin']}/sims",
        num_results=max(1, min(int(args.get("num_results", 10)), 25)),
        response_groups=CATALOGUE_RESPONSE_GROUPS,
    )
    items = sims.get("similar_products") or sims.get("products") or []
    return [summarise(i) for i in items]


def cmd_search(client, args):
    res = client.get(
        "catalog/products",
        keywords=args["keywords"],
        num_results=max(1, min(int(args.get("num_results", 10)), 50)),
        response_groups=CATALOGUE_RESPONSE_GROUPS,
    )
    return [summarise(i) for i in res.get("products", [])]


def cmd_stats(client, args):
    from dateutil.relativedelta import relativedelta

    months = max(1, min(int(args.get("months", 6)), 12))
    start = (datetime.now(timezone.utc) - relativedelta(months=months - 1)).replace(day=1)
    return client.get(
        "stats/aggregates",
        monthly_listening_interval_duration=str(months),
        monthly_listening_interval_start_date=start.strftime("%Y-%m-%d"),
        response_groups="total_listening_stats",
        store="Audible",
        locale="en_GB",
    )


COMMANDS = {
    "library": cmd_library,
    "finished": cmd_finished,
    "similar": cmd_similar,
    "search": cmd_search,
    "stats": cmd_stats,
}


def main() -> int:
    command = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    auth_file = args.pop("auth_file")
    client = _client(auth_file)
    result = COMMANDS[command](client, args)
    json.dump(result, sys.stdout, default=str, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
