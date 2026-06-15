"""
On-demand energy charts: generates PNG graphs and posts to Discord.

Usage:
  python chart.py usage          # Daily usage bar chart (last 30 days)
  python chart.py peak           # Peak vs off-peak breakdown (last 30 days)
  python chart.py both           # Both charts (default)
"""
import io
import os
import sys
from datetime import date, timedelta

import httpx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from supabase import create_client

from .config import SUPABASE_URL, SUPABASE_KEY, DISCORD_ENERGY_WEBHOOK


def get_daily_data(sb, days: int = 30) -> dict:
    """Fetch daily summaries for the last N days."""
    from_date = (date.today() - timedelta(days=days)).isoformat()
    result = (
        sb.table("energy_daily_summary")
        .select("*")
        .gte("summary_date", from_date)
        .order("summary_date")
        .execute()
    )
    elec = [r for r in result.data if r["fuel_type"] == "electricity"]
    gas = [r for r in result.data if r["fuel_type"] == "gas"]
    return {"electricity": elec, "gas": gas}


def chart_usage(data: dict) -> io.BytesIO:
    """Generate daily usage stacked bar chart."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    fig.suptitle(f"Daily Energy Usage — Last {len(data['electricity'])} Days", fontsize=14, fontweight="bold")

    # Electricity
    elec = data["electricity"]
    dates_e = [date.fromisoformat(r["summary_date"]) for r in elec]
    kwh_e = [r["total_kwh"] for r in elec]
    costs_e = [r["total_cost_pence"] / 100 for r in elec]
    ev_days = [r["is_ev_charge_day"] for r in elec]

    colors_e = ["#22c55e" if ev else "#3b82f6" for ev in ev_days]
    ax1.bar(dates_e, kwh_e, color=colors_e, alpha=0.8, width=0.8)
    ax1.set_ylabel("kWh", fontsize=11)
    ax1.set_title("Electricity (blue = normal, green = EV charge day)", fontsize=10, color="#666")
    ax1.axhline(y=sum(kwh_e) / len(kwh_e) if kwh_e else 0, color="#ef4444", linestyle="--", alpha=0.5, label="Average")
    ax1.legend(fontsize=9)
    ax1.grid(axis="y", alpha=0.3)

    # Cost labels on the right axis
    ax1_cost = ax1.twinx()
    ax1_cost.set_ylabel("£", fontsize=11)
    ax1_cost.set_ylim(0, max(costs_e) * 1.15 if costs_e else 1)
    ax1_cost.plot(dates_e, costs_e, color="#f97316", linewidth=1.5, alpha=0.7, marker=".", markersize=3)

    # Gas
    gas = data["gas"]
    dates_g = [date.fromisoformat(r["summary_date"]) for r in gas]
    kwh_g = [r["total_kwh"] for r in gas]
    costs_g = [r["total_cost_pence"] / 100 for r in gas]

    ax2.bar(dates_g, kwh_g, color="#f59e0b", alpha=0.8, width=0.8)
    ax2.set_ylabel("kWh", fontsize=11)
    ax2.set_title("Gas", fontsize=10, color="#666")
    ax2.axhline(y=sum(kwh_g) / len(kwh_g) if kwh_g else 0, color="#ef4444", linestyle="--", alpha=0.5, label="Average")
    ax2.legend(fontsize=9)
    ax2.grid(axis="y", alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax2.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha="right")

    ax2_cost = ax2.twinx()
    ax2_cost.set_ylabel("£", fontsize=11)
    ax2_cost.set_ylim(0, max(costs_g) * 1.15 if costs_g else 1)
    ax2_cost.plot(dates_g, costs_g, color="#f97316", linewidth=1.5, alpha=0.7, marker=".", markersize=3)

    # Totals annotation
    total_kwh = sum(kwh_e) + sum(kwh_g)
    total_cost = sum(costs_e) + sum(costs_g)
    fig.text(0.5, 0.01, f"Total: {total_kwh:.0f} kWh / £{total_cost:.2f}", ha="center", fontsize=11, color="#666")

    plt.tight_layout(rect=[0, 0.03, 1, 0.96])

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def chart_peak_offpeak(data: dict) -> io.BytesIO:
    """Generate peak vs off-peak electricity breakdown."""
    elec = data["electricity"]
    dates = [date.fromisoformat(r["summary_date"]) for r in elec]
    peak = [r["peak_kwh"] for r in elec]
    offpeak = [r["offpeak_kwh"] for r in elec]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), gridspec_kw={"height_ratios": [3, 1]})
    fig.suptitle(f"Electricity Peak vs Off-Peak — Last {len(elec)} Days", fontsize=14, fontweight="bold")

    # Stacked bar chart
    ax1.bar(dates, peak, color="#ef4444", alpha=0.8, width=0.8, label=f"Peak (29.6p/kWh)")
    ax1.bar(dates, offpeak, bottom=peak, color="#22c55e", alpha=0.8, width=0.8, label=f"Off-peak (7.0p/kWh)")
    ax1.set_ylabel("kWh", fontsize=11)
    ax1.legend(fontsize=10)
    ax1.grid(axis="y", alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax1.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha="right")

    # Summary stats
    total_peak = sum(peak)
    total_offpeak = sum(offpeak)
    total = total_peak + total_offpeak
    pct_offpeak = (total_offpeak / total * 100) if total > 0 else 0

    ev_days = sum(1 for r in elec if r["is_ev_charge_day"])
    peak_cost = total_peak * 29.6 / 100  # approx
    offpeak_cost = total_offpeak * 7.0 / 100  # approx

    # Pie chart of peak vs off-peak
    sizes = [total_peak, total_offpeak]
    labels = [f"Peak\n{total_peak:.0f} kWh\n~£{peak_cost:.0f}", f"Off-peak\n{total_offpeak:.0f} kWh\n~£{offpeak_cost:.0f}"]
    colors = ["#ef4444", "#22c55e"]
    ax2.pie(sizes, labels=labels, colors=colors, autopct="%1.0f%%", startangle=90,
            textprops={"fontsize": 10})
    ax2.set_title(f"{ev_days} EV charge days | {pct_offpeak:.0f}% off-peak usage", fontsize=10, color="#666")

    plt.tight_layout(rect=[0, 0, 1, 0.96])

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def post_chart_to_discord(buf: io.BytesIO, filename: str, message: str = ""):
    """Post a chart image to Discord via webhook."""
    files = {"file": (filename, buf, "image/png")}
    payload = {}
    if message:
        payload["content"] = message

    resp = httpx.post(DISCORD_ENERGY_WEBHOOK, data=payload, files=files, timeout=30)
    resp.raise_for_status()
    print(f"  Posted {filename} to Discord")


def main():
    if not SUPABASE_KEY:
        print("ERROR: SUPABASE_SERVICE_ROLE_KEY not found")
        sys.exit(1)

    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    print("Generating energy charts...")
    data = get_daily_data(sb, days=30)

    if not data["electricity"]:
        print("No electricity data found")
        sys.exit(1)

    if mode in ("usage", "both"):
        buf = chart_usage(data)
        post_chart_to_discord(buf, "energy-usage.png", "**Daily Energy Usage — Last 30 Days**")

    if mode in ("peak", "both"):
        buf = chart_peak_offpeak(data)
        post_chart_to_discord(buf, "energy-peak-offpeak.png", "**Peak vs Off-Peak Breakdown**")

    print("Done.")


if __name__ == "__main__":
    main()
