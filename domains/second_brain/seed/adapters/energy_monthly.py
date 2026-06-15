"""Monthly home-energy summaries into Second Brain.

One item per complete calendar month from energy_daily_summary — kWh and £
by fuel, peak/off-peak split, EV charge days — so Peter can answer "what
did we spend on electricity in March?" from knowledge search, and the
household's energy history survives in the brain alongside everything else.

Runner dedupe by source_url (energy://monthly/YYYY-MM) means each month
imports once, after it completes.
"""

from collections import defaultdict
from datetime import date, datetime, timezone

import httpx

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter
from domains.energy.config import SUPABASE_KEY, SUPABASE_URL

_SB_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


@register_adapter
class EnergyMonthlyAdapter(SeedAdapter):
    """Monthly electricity/gas summaries from energy_daily_summary."""

    name = "energy-monthly"
    description = "Monthly home energy summaries (kWh, cost, EV days) into Second Brain"
    source_system = "seed:energy"

    async def validate(self) -> tuple[bool, str]:
        return True, ""

    async def fetch(self, limit: int = 24) -> list[SeedItem]:
        import asyncio
        return await asyncio.to_thread(self._fetch_sync, limit)

    def _fetch_sync(self, limit: int) -> list[SeedItem]:
        resp = httpx.get(
            f"{SUPABASE_URL}/rest/v1/energy_daily_summary",
            headers=_SB_HEADERS,
            params={
                "select": "summary_date,fuel_type,total_kwh,peak_kwh,offpeak_kwh,"
                          "total_cost_pence,is_ev_charge_day",
                "order": "summary_date.desc",
                "limit": "3000",
            },
            timeout=30,
        )
        if resp.status_code != 200:
            logger.warning(f"energy-monthly: summary fetch {resp.status_code}")
            return []

        this_month = date.today().strftime("%Y-%m")
        months: dict[str, list[dict]] = defaultdict(list)
        for r in resp.json():
            month = r["summary_date"][:7]
            if month < this_month:  # complete months only
                months[month].append(r)

        items: list[SeedItem] = []
        for month, rows in sorted(months.items()):
            elec = [r for r in rows if r["fuel_type"] == "electricity"]
            gas = [r for r in rows if r["fuel_type"] == "gas"]
            # skip sparse months (partial first month of data)
            if len(elec) < 20:
                continue

            e_kwh = sum(float(r["total_kwh"]) for r in elec)
            e_cost = sum(float(r["total_cost_pence"]) for r in elec) / 100
            e_off = sum(float(r["offpeak_kwh"] or 0) for r in elec)
            g_kwh = sum(float(r["total_kwh"]) for r in gas)
            g_cost = sum(float(r["total_cost_pence"]) for r in gas) / 100
            ev_days = sum(1 for r in elec if r.get("is_ev_charge_day"))
            label = date.fromisoformat(f"{month}-01").strftime("%B %Y")

            items.append(SeedItem(
                title=f"Home Energy — {label}",
                content="\n".join([
                    f"# Home Energy — {label}",
                    "",
                    f"**Electricity:** {e_kwh:.0f} kWh, £{e_cost:.2f} "
                    f"({e_off:.0f} kWh off-peak, {ev_days} EV charge days)",
                    f"**Gas:** {g_kwh:.0f} kWh, £{g_cost:.2f}",
                    f"**Total:** £{e_cost + g_cost:.2f}",
                    "",
                    f"Daily averages: electricity {e_kwh / len(elec):.1f} kWh, "
                    f"gas {g_kwh / max(len(gas), 1):.1f} kWh "
                    f"({len(elec)} days of data this month).",
                ]),
                source_url=f"energy://monthly/{month}",
                topics=["energy", "home", "utilities", "monthly-summary"],
                created_at=datetime.now(timezone.utc) if month == this_month
                else datetime.fromisoformat(f"{month}-28T12:00:00+00:00"),
                metadata={"month": month, "elec_kwh": round(e_kwh, 1),
                          "gas_kwh": round(g_kwh, 1),
                          "total_cost_pounds": round(e_cost + g_cost, 2),
                          "ev_days": ev_days},
                content_type="note",
            ))
        return items[:limit]

    def get_default_topics(self) -> list[str]:
        return ["energy", "home"]
