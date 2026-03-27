"""Financial data API endpoints — belt-and-braces fallback for financial-data MCP.

Exposes the same 12 financial tools as HTTP endpoints so Peter can access
financial data via curl when MCP servers aren't available.

All functions return pre-formatted markdown strings (same output as MCP tools).
"""

import os
import sys
from typing import Optional

from fastapi import APIRouter, Query

# Add project root and mcp_servers dir to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MCP_SERVERS_DIR = os.path.join(PROJECT_ROOT, "mcp_servers")
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, MCP_SERVERS_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

router = APIRouter(prefix="/finance", tags=["finance"])


# ---------------------------------------------------------------------------
# Lazy imports — avoid loading heavy deps at module level
# ---------------------------------------------------------------------------

def _personal():
    from financial_data.personal_finance import (
        net_worth, budget_status, spending_by_category, savings_rate,
        fire_status, find_recurring, search_transactions, transactions_by_category,
    )
    return {
        "net_worth": net_worth,
        "budget_status": budget_status,
        "spending_by_category": spending_by_category,
        "savings_rate": savings_rate,
        "fire_status": fire_status,
        "find_recurring": find_recurring,
        "search_transactions": search_transactions,
        "transactions_by_category": transactions_by_category,
    }


def _business():
    from financial_data.business_finance import business_pnl, platform_revenue
    return {"business_pnl": business_pnl, "platform_revenue": platform_revenue}


# ---------------------------------------------------------------------------
# Personal Finance
# ---------------------------------------------------------------------------

@router.get("/net-worth")
async def get_net_worth():
    """Current net worth across all accounts."""
    return {"result": await _personal()["net_worth"]()}


@router.get("/budget")
async def get_budget_status(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
):
    """Budget status — overall and by category."""
    return {"result": await _personal()["budget_status"](year, month)}


@router.get("/spending")
async def get_spending_by_category(
    period: str = Query("this_month"),
    category: Optional[str] = Query(None, alias="category_name"),
):
    """Spending breakdown by category."""
    return {"result": await _personal()["spending_by_category"](period, category)}


@router.get("/savings-rate")
async def get_savings_rate(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
):
    """Savings rate calculation."""
    return {"result": await _personal()["savings_rate"](year, month)}


@router.get("/fire")
async def get_fire_status(
    scenario: Optional[str] = Query(None, alias="scenario_name"),
):
    """FIRE (Financial Independence, Retire Early) progress."""
    return {"result": await _personal()["fire_status"](scenario)}


@router.get("/recurring")
async def find_recurring_transactions(
    min_occurrences: int = Query(3),
    months: int = Query(6),
):
    """Find recurring transactions (subscriptions, regular payments)."""
    return {"result": await _personal()["find_recurring"](min_occurrences, months)}


@router.get("/search")
async def search_transactions(
    query: str = Query(...),
    period: str = Query("this_year"),
    limit: int = Query(50),
):
    """Search transactions by description."""
    return {"result": await _personal()["search_transactions"](query, period, limit)}


@router.get("/transactions")
async def get_transactions_by_category(
    category: str = Query(..., alias="category_name"),
    period: str = Query("this_year"),
    limit: int = Query(50),
):
    """List transactions for a specific category."""
    return {"result": await _personal()["transactions_by_category"](category, period, limit)}


# ---------------------------------------------------------------------------
# Business Finance (Hadley Bricks)
# ---------------------------------------------------------------------------

@router.get("/business/pnl")
async def get_business_pnl(
    start_month: Optional[str] = Query(None),
    end_month: Optional[str] = Query(None),
):
    """Hadley Bricks P&L statement."""
    return {"result": await _business()["business_pnl"](start_month, end_month)}


@router.get("/business/revenue")
async def get_platform_revenue(
    platform: Optional[str] = Query(None),
    period: str = Query("this_month"),
):
    """Revenue breakdown by platform (eBay, Amazon, BrickLink, Brick Owl)."""
    return {"result": await _business()["platform_revenue"](platform, period)}


# ---------------------------------------------------------------------------
# Comparison & Overview
# ---------------------------------------------------------------------------

@router.get("/compare")
async def compare_spending(
    period_a: str = Query(...),
    period_b: str = Query(...),
):
    """Compare spending between two periods."""
    from financial_data.config import get_date_range
    from financial_data.supabase_client import finance_rpc, finance_query
    from financial_data.formatters import gbp, md_table, safe_float, period_label

    excluded_cats = await finance_query("categories", {
        "exclude_from_totals": "eq.true",
        "select": "id",
    })
    excluded_ids = [c["id"] for c in excluded_cats]

    start_a, end_a = get_date_range(period_a)
    start_b, end_b = get_date_range(period_b)

    rows_a = await finance_rpc("get_spending_by_category", {
        "start_date": start_a, "end_date": end_a, "excluded_ids": excluded_ids,
    })
    rows_b = await finance_rpc("get_spending_by_category", {
        "start_date": start_b, "end_date": end_b, "excluded_ids": excluded_ids,
    })

    map_a = {r["category_name"]: safe_float(r["total_amount"]) for r in rows_a}
    map_b = {r["category_name"]: safe_float(r["total_amount"]) for r in rows_b}
    all_cats = sorted(set(map_a.keys()) | set(map_b.keys()))

    table_rows = []
    for cat in all_cats:
        a, b = map_a.get(cat, 0), map_b.get(cat, 0)
        table_rows.append([cat, gbp(a), gbp(b), gbp(a - b, show_sign=True)])

    total_a, total_b = sum(map_a.values()), sum(map_b.values())
    table_rows.append(["**Total**", f"**{gbp(total_a)}**", f"**{gbp(total_b)}**",
                        f"**{gbp(total_a - total_b, show_sign=True)}**"])

    output = f"# Spending Comparison: {period_label(period_a)} vs {period_label(period_b)}\n\n"
    output += md_table(["Category", period_label(period_a), period_label(period_b), "Difference"], table_rows)
    return {"result": output}


@router.get("/health")
async def get_financial_health():
    """Comprehensive financial overview — net worth, budget, savings, FIRE, business P&L."""
    pf = _personal()
    bf = _business()

    sections = []
    for name, fn, args in [
        ("Net Worth", pf["net_worth"], ()),
        ("Budget Status", pf["budget_status"], (None, None)),
        ("Savings Rate", pf["savings_rate"], (None, None)),
        ("FIRE Status", pf["fire_status"], (None,)),
        ("Business P&L", bf["business_pnl"], (None, None)),
    ]:
        try:
            sections.append(await fn(*args))
        except Exception as e:
            sections.append(f"## {name}\n\nFailed to load: {e}")

    return {"result": "\n\n---\n\n".join(sections)}
