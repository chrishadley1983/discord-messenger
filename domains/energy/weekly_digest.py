"""
Weekly energy digest: posts a summary of the past week's energy usage
to Discord #energy channel.

Run weekly Sunday 9AM via Peter bot.
"""
import os
import sys
from datetime import date, timedelta

import httpx
from supabase import create_client

from .config import SUPABASE_URL, SUPABASE_KEY, DISCORD_ENERGY_WEBHOOK


def main():
    if not SUPABASE_KEY:
        print("ERROR: SUPABASE_SERVICE_ROLE_KEY not found")
        sys.exit(1)

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    today = date.today()

    # This week = last 7 days (Mon-Sun)
    week_end = today
    week_start = today - timedelta(days=7)

    # Previous week for comparison
    prev_end = week_start
    prev_start = week_start - timedelta(days=7)

    lines = [f"**Weekly Energy Digest** \u2014 {week_start.strftime('%d %b')} to {week_end.strftime('%d %b')}\n"]

    for fuel in ["electricity", "gas"]:
        emoji = "\u26a1" if fuel == "electricity" else "\U0001f525"

        # This week
        this_week = (
            sb.table("energy_daily_summary")
            .select("*")
            .eq("fuel_type", fuel)
            .gte("summary_date", week_start.isoformat())
            .lt("summary_date", week_end.isoformat())
            .order("summary_date")
            .execute()
        )

        # Previous week
        prev_week = (
            sb.table("energy_daily_summary")
            .select("total_kwh, total_cost_pence, is_ev_charge_day")
            .eq("fuel_type", fuel)
            .gte("summary_date", prev_start.isoformat())
            .lt("summary_date", prev_end.isoformat())
            .execute()
        )

        if not this_week.data:
            lines.append(f"{emoji} **{fuel.title()}**: No data this week")
            continue

        tw_kwh = sum(d["total_kwh"] for d in this_week.data)
        tw_cost = sum(d["total_cost_pence"] for d in this_week.data) / 100
        tw_days = len(this_week.data)
        tw_avg_kwh = tw_kwh / tw_days if tw_days else 0

        line = f"{emoji} **{fuel.title()}**: {tw_kwh:.0f} kWh = **\u00a3{tw_cost:.2f}** ({tw_days} days, avg {tw_avg_kwh:.1f} kWh/day)"

        # Week-over-week comparison
        if prev_week.data:
            pw_kwh = sum(d["total_kwh"] for d in prev_week.data)
            pw_cost = sum(d["total_cost_pence"] for d in prev_week.data) / 100
            if pw_kwh > 0:
                kwh_change = ((tw_kwh - pw_kwh) / pw_kwh) * 100
                arrow = "\u2b06\ufe0f" if kwh_change > 0 else "\u2b07\ufe0f"
                line += f"\n  vs last week: {arrow} {abs(kwh_change):.0f}% ({pw_kwh:.0f} kWh / \u00a3{pw_cost:.2f})"

        lines.append(line)

        # EV summary for electricity
        if fuel == "electricity":
            ev_days = [d for d in this_week.data if d.get("is_ev_charge_day")]
            if ev_days:
                ev_kwh = sum(d["offpeak_kwh"] for d in ev_days)
                ev_cost = sum(d["total_cost_pence"] for d in ev_days) / 100
                lines.append(f"  \U0001f50c EV charged {len(ev_days)} days ({ev_kwh:.0f} kWh off-peak, \u00a3{ev_cost:.2f} total)")

        # Peak day
        peak_day = max(this_week.data, key=lambda d: d["total_kwh"])
        peak_date = date.fromisoformat(peak_day["summary_date"])
        lines.append(f"  Peak: {peak_date.strftime('%A')} {peak_day['total_kwh']:.1f} kWh (\u00a3{peak_day['total_cost_pence'] / 100:.2f})")

    # Month-to-date
    first_of_month = today.replace(day=1)
    mtd = (
        sb.table("energy_daily_summary")
        .select("total_cost_pence")
        .gte("summary_date", first_of_month.isoformat())
        .execute()
    )
    if mtd.data:
        mtd_total = sum(r["total_cost_pence"] for r in mtd.data) / 100
        mtd_days = (today - first_of_month).days
        lines.append(f"\n\U0001f4c5 **{today.strftime('%B')} MTD**: \u00a3{mtd_total:.2f} ({mtd_days} days)")

    # Heating efficiency (gas per degree-day vs 4-week baseline)
    try:
        from .heating import weekly_line
        _heating = weekly_line()
        if _heating:
            lines.append('')
            lines.append(_heating)
    except Exception as _e:
        print(f'heating line skipped: {_e}')

    message = "\n".join(lines)
    print(message.encode("ascii", errors="replace").decode())

    try:
        httpx.post(DISCORD_ENERGY_WEBHOOK, json={"content": message}, timeout=10)
        print("\nPosted weekly digest to Discord #energy")
    except Exception as e:
        print(f"Discord webhook error: {e}")


if __name__ == "__main__":
    main()
