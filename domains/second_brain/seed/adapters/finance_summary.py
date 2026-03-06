"""Finance Summary seed adapter — generates monthly financial summaries.

Runs on 2nd of each month, creates a comprehensive financial summary of
the previous month and saves it to Second Brain for historical search.

For backfill of past months, uses wealth_snapshots for historical net worth
rather than live account balances.
"""

from __future__ import annotations

import calendar
import os
import sys
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter

# Ensure mcp_servers package is importable
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if os.path.join(_PROJECT_ROOT, "mcp_servers") not in sys.path:
    sys.path.insert(0, os.path.join(_PROJECT_ROOT, "mcp_servers"))

from dotenv import load_dotenv
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))


@register_adapter
class FinanceSummaryAdapter(SeedAdapter):
    """Generate monthly financial summaries for Second Brain."""

    name = "finance-summary"
    description = "Monthly financial summary (net worth, budget, savings, business P&L)"
    source_system = "seed:finance"

    def __init__(self, config: dict[str, Any] = None):
        super().__init__(config)
        self._year = self.config.get("year")
        self._month = self.config.get("month")

    async def validate(self) -> tuple[bool, str]:
        from financial_data.config import API_KEY
        if not API_KEY:
            return False, "No Supabase key configured (SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY)"
        return True, ""

    def get_default_topics(self) -> list[str]:
        return ["finance", "monthly-review", "net-worth", "budget"]

    async def fetch(self, limit: int = 1) -> list[SeedItem]:
        """Generate financial summary for the target month."""
        today = date.today()

        if self._year and self._month:
            year, month = self._year, self._month
        else:
            if today.month == 1:
                year, month = today.year - 1, 12
            else:
                year, month = today.year, today.month - 1

        is_current = (year == today.year and month == today.month) or (
            year == today.year and month == today.month - 1 and today.day <= 3
        )

        source_id = f"finance-summary-{year}-{month:02d}"
        sections = []

        # --- Net Worth (historical from snapshots, or live for current) ---
        try:
            if is_current:
                from financial_data.personal_finance import net_worth
                sections.append(await net_worth())
            else:
                sections.append(await self._historical_net_worth(year, month))
        except Exception as e:
            sections.append(f"## Net Worth\n_Unavailable: {e}_")

        # --- Budget ---
        try:
            from financial_data.personal_finance import budget_status
            sections.append(await budget_status(year, month))
        except Exception as e:
            sections.append(f"## Budget\n_Unavailable: {e}_")

        # --- Savings Rate ---
        try:
            from financial_data.personal_finance import savings_rate
            sections.append(await savings_rate(year, month))
        except Exception as e:
            sections.append(f"## Savings Rate\n_Unavailable: {e}_")

        # --- FIRE Progress (only for recent months — needs live portfolio) ---
        if year >= today.year - 1:
            try:
                from financial_data.personal_finance import fire_status
                sections.append(await fire_status())
            except Exception as e:
                sections.append(f"## FIRE Progress\n_Unavailable: {e}_")

        # --- Business P&L (only if business data exists — late 2023+) ---
        if year >= 2023 and (year > 2023 or month >= 12):
            try:
                from financial_data.business_finance import business_pnl
                month_str = f"{year}-{month:02d}"
                sections.append(await business_pnl(month_str, month_str))
            except Exception as e:
                sections.append(f"## Hadley Bricks P&L\n_Unavailable: {e}_")

        content = "\n\n---\n\n".join(sections)
        title = f"Financial Summary — {year}-{month:02d}"

        return [
            SeedItem(
                title=title,
                content=content,
                source_url=f"internal://finance-summary/{year}-{month:02d}",
                source_id=source_id,
                topics=["finance", "monthly-review", "net-worth", "budget", "hadley-bricks"],
                created_at=datetime(year, month, 1),
                metadata={
                    "year": year,
                    "month": month,
                    "content_type": "note",
                },
            )
        ]

    async def _historical_net_worth(self, year: int, month: int) -> str:
        """Build net worth section from wealth_snapshots for a specific month."""
        from financial_data.supabase_client import finance_query
        from financial_data.formatters import gbp, change_str, md_table, safe_float

        target_date = date(year, month, 1).isoformat()

        # Get snapshots for this month
        snapshots = await finance_query("wealth_snapshots", {
            "date": f"eq.{target_date}",
            "select": "account_id,balance,date",
        }, paginate=True)

        if not snapshots:
            # Try last day of month
            last_day = date(year, month, calendar.monthrange(year, month)[1]).isoformat()
            snapshots = await finance_query("wealth_snapshots", {
                "date": f"lte.{last_day}",
                "and": f"(date.gte.{target_date})",
                "select": "account_id,balance,date",
            }, paginate=True)

        if not snapshots:
            return f"## Net Worth — {year}-{month:02d}\n_No snapshot data for this month_"

        # Get account details
        account_ids = list(set(s["account_id"] for s in snapshots))
        accounts = await finance_query("accounts", {
            "id": f"in.({','.join(account_ids)})",
            "select": "id,name,type,include_in_net_worth",
        }, paginate=True)

        acc_map = {a["id"]: a for a in accounts}

        # Build totals
        by_type: dict[str, float] = defaultdict(float)
        by_account: list[dict] = []
        total = 0.0

        for s in snapshots:
            acc = acc_map.get(s["account_id"], {})
            if not acc.get("include_in_net_worth", True):
                continue
            bal = safe_float(s.get("balance"))
            acc_type = acc.get("type", "other")
            by_type[acc_type] += bal
            total += bal
            by_account.append({"name": acc.get("name", "Unknown"), "type": acc_type, "balance": bal})

        # Previous month for comparison
        if month == 1:
            prev_y, prev_m = year - 1, 12
        else:
            prev_y, prev_m = year, month - 1
        prev_date = date(prev_y, prev_m, 1).isoformat()

        prev_snaps = await finance_query("wealth_snapshots", {
            "date": f"eq.{prev_date}",
            "select": "account_id,balance",
        }, paginate=True)

        prev_total = 0.0
        for s in prev_snaps:
            acc = acc_map.get(s["account_id"], {})
            if acc.get("include_in_net_worth", True):
                prev_total += safe_float(s.get("balance"))

        # Format
        type_labels = {
            "current": "Current Accounts", "savings": "Savings",
            "investment": "Investments", "pension": "Pensions",
            "isa": "ISAs", "property": "Property",
            "credit": "Credit Cards", "other": "Other",
        }

        rows = []
        for t in ["current", "savings", "isa", "investment", "pension", "property", "credit", "other"]:
            if t in by_type:
                rows.append([type_labels.get(t, t), gbp(by_type[t])])

        output = f"# Net Worth — {year}-{month:02d}\n\n"
        output += f"**Total: {gbp(total)}**"
        if prev_total:
            output += f"  ({change_str(total, prev_total)} vs previous month)"
        output += f"\n_From wealth snapshot dated {target_date}_\n\n"
        output += md_table(["Type", "Balance"], rows)

        by_account.sort(key=lambda a: abs(a["balance"]), reverse=True)
        if by_account[:10]:
            output += "\n\n### Top Accounts\n"
            acc_rows = [[a["name"], a["type"], gbp(a["balance"])] for a in by_account[:10]]
            output += md_table(["Account", "Type", "Balance"], acc_rows)

        return output
