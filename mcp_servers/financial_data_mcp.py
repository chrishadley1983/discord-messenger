"""MCP Server for Financial Data — personal finance + Hadley Bricks business.

Provides read-only access to Chris's financial data across two Supabase schemas:
- finance schema: personal accounts, budgets, transactions, FIRE planning
- public schema: Hadley Bricks business transactions (eBay, Amazon, BrickLink, Brick Owl)

Usage:
    python mcp_servers/financial_data_mcp.py
"""

import os
import sys
from datetime import date

# Add project root and mcp_servers dir to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MCP_SERVERS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, MCP_SERVERS_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from mcp.server.fastmcp import FastMCP

# Import financial data modules
from financial_data.personal_finance import (
    net_worth,
    budget_status,
    spending_by_category,
    savings_rate,
    fire_status,
    find_recurring,
    search_transactions,
    transactions_by_category,
)
from financial_data.business_finance import (
    business_pnl,
    platform_revenue,
)
from financial_data.subscriptions import (
    add_subscription as _add_sub,
    update_subscription as _update_sub,
    cancel_subscription as _cancel_sub,
    dismiss_recurring_alert as _dismiss_alert,
    accept_price_change as _accept_price,
    list_subscriptions as _list_subs,
)
from financial_data.formatters import period_label

mcp = FastMCP(
    "financial-data",
    instructions=(
        "Chris's financial data across personal accounts and Hadley Bricks LEGO business. "
        "Use these tools when Chris asks about net worth, budgets, spending, savings rate, "
        "FIRE progress, business P&L, platform revenue, or wants to search transactions. "
        "All data is read-only and live from Supabase."
    ),
)


# =============================================================================
# PERSONAL FINANCE TOOLS
# =============================================================================

@mcp.tool()
async def get_net_worth() -> str:
    """Get Chris's current net worth with breakdown by account type.

    Shows total net worth, change vs last month, breakdown by type (current,
    savings, ISAs, investments, pensions, property, credit), and top accounts.

    Use when Chris asks: "What's my net worth?", "How much am I worth?",
    "Show me my account balances"
    """
    try:
        return await net_worth()
    except Exception as e:
        return f"Failed to get net worth: {e}"


@mcp.tool()
async def get_budget_status(year: int | None = None, month: int | None = None) -> str:
    """Get budget vs actual comparison for a month.

    Shows income and expenses against budget, highlights over/under budget
    categories, and provides full category breakdown.

    Args:
        year: Year (default: current year)
        month: Month 1-12 (default: current month)

    Use when Chris asks: "Am I on budget?", "How's my budget this month?",
    "What did I overspend on?"
    """
    try:
        return await budget_status(year, month)
    except Exception as e:
        return f"Failed to get budget status: {e}"


@mcp.tool()
async def get_spending_by_category(
    period: str = "this_month",
    category_name: str | None = None,
) -> str:
    """Get spending breakdown by category for a time period.

    Args:
        period: One of: this_month, last_month, this_quarter, last_quarter,
                this_year, last_year, all_time
        category_name: Optional filter — show only categories matching this name

    Use when Chris asks: "How much on eating out?", "Where's my money going?",
    "Spending breakdown this month"
    """
    try:
        return await spending_by_category(period, category_name)
    except Exception as e:
        return f"Failed to get spending: {e}"


@mcp.tool()
async def get_savings_rate(year: int | None = None, month: int | None = None) -> str:
    """Get savings rate for a month — actual vs budget.

    Shows income, expenses, savings amount, and savings rate percentage
    compared to budget targets.

    Args:
        year: Year (default: current year)
        month: Month 1-12 (default: current month)

    Use when Chris asks: "What's my savings rate?", "Am I saving enough?"
    """
    try:
        return await savings_rate(year, month)
    except Exception as e:
        return f"Failed to get savings rate: {e}"


@mcp.tool()
async def get_fire_status(scenario_name: str | None = None) -> str:
    """Get FIRE (Financial Independence, Retire Early) status and projections.

    Shows portfolio value, FI target number, progress %, Coast FI number,
    years to FI, and scenario comparisons.

    Args:
        scenario_name: Optional — filter to a specific named scenario

    Use when Chris asks: "When can I retire?", "FIRE progress",
    "How close am I to financial independence?"
    """
    try:
        return await fire_status(scenario_name)
    except Exception as e:
        return f"Failed to get FIRE status: {e}"


@mcp.tool()
async def find_recurring_transactions(min_occurrences: int = 3, months: int = 6) -> str:
    """Find recurring transactions like subscriptions and regular payments.

    Analyses transaction descriptions to identify patterns — groups by
    normalised description and shows frequency + average amount.

    Args:
        min_occurrences: Minimum times a transaction must appear (default: 3)
        months: How many months back to search (default: 6)

    Use when Chris asks: "What subscriptions do I pay?",
    "Show me recurring payments", "What direct debits do I have?"
    """
    try:
        return await find_recurring(min_occurrences, months)
    except Exception as e:
        return f"Failed to find recurring transactions: {e}"


@mcp.tool()
async def search_transactions_tool(
    query: str,
    period: str = "this_year",
    limit: int = 50,
) -> str:
    """Search personal finance transactions by description.

    Searches transaction descriptions using case-insensitive matching.

    Args:
        query: Search term (e.g. "Tesco", "Netflix", "mortgage")
        period: One of: this_month, last_month, this_quarter, this_year, all_time
        limit: Max results (default: 50)

    Use when Chris asks: "Find all Tesco transactions",
    "How much at Costa this year?", "Search for Netflix payments"
    """
    try:
        return await search_transactions(query, period, limit)
    except Exception as e:
        return f"Failed to search transactions: {e}"


@mcp.tool()
async def get_transactions_by_category(
    category_name: str,
    period: str = "this_year",
    limit: int = 50,
) -> str:
    """Get all transactions in a specific spending category.

    Use this when you know the category name (from get_spending_by_category)
    and want to see the individual transactions within it.

    Args:
        category_name: Category name or partial match (e.g. "Takeaway", "Eating out",
                       "Groceries", "Entertainment"). Case-insensitive.
        period: One of: this_month, last_month, this_quarter, this_year, all_time
        limit: Max results (default: 50)

    Use when Chris asks: "Show all takeaway transactions", "What did I spend
    on eating out?", "List my grocery spending this month"
    """
    try:
        return await transactions_by_category(category_name, period, limit)
    except Exception as e:
        return f"Failed to get transactions by category: {e}"


# =============================================================================
# BUSINESS FINANCE TOOLS
# =============================================================================

@mcp.tool()
async def get_business_pnl(
    start_month: str | None = None,
    end_month: str | None = None,
) -> str:
    """Get Hadley Bricks LEGO business Profit & Loss statement.

    Shows revenue by platform (eBay, Amazon, BrickLink, Brick Owl) with fees
    and refunds broken out, plus all cost categories (stock, postage, packing,
    subscriptions, mileage, home costs).

    Args:
        start_month: Start as YYYY-MM (default: current month)
        end_month: End as YYYY-MM (default: current month)

    Use when Chris asks: "How's the business doing?", "P&L this month",
    "Business profit", "Hadley Bricks performance"
    """
    try:
        return await business_pnl(start_month, end_month)
    except Exception as e:
        return f"Failed to get business P&L: {e}"


@mcp.tool()
async def get_platform_revenue(
    platform: str | None = None,
    period: str = "this_month",
) -> str:
    """Get revenue breakdown by selling platform.

    Shows gross sales, refunds, fees, and net revenue per platform.

    Args:
        platform: Optional — "ebay", "amazon", "bricklink", or "brickowl".
                  If omitted, shows all platforms.
        period: One of: this_month, last_month, this_quarter, this_year, all_time

    Use when Chris asks: "Amazon revenue this month", "eBay vs Amazon",
    "Which platform makes the most?"
    """
    try:
        return await platform_revenue(platform, period)
    except Exception as e:
        return f"Failed to get platform revenue: {e}"


# =============================================================================
# CROSS-DOMAIN TOOLS
# =============================================================================

@mcp.tool()
async def compare_spending(period_a: str, period_b: str) -> str:
    """Compare spending between two time periods.

    Shows category-by-category comparison with differences highlighted.

    Args:
        period_a: First period (e.g. "this_month", "last_month")
        period_b: Second period to compare against

    Use when Chris asks: "Compare March vs February spending",
    "How does this month compare to last?"
    """
    try:
        from financial_data.config import get_date_range
        from financial_data.supabase_client import finance_rpc, finance_query
        from financial_data.formatters import gbp, md_table, safe_float, period_label

        # Get excluded categories
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

        # Build lookup
        map_a = {r["category_name"]: safe_float(r["total_amount"]) for r in rows_a}
        map_b = {r["category_name"]: safe_float(r["total_amount"]) for r in rows_b}

        all_cats = sorted(set(map_a.keys()) | set(map_b.keys()))

        table_rows = []
        for cat in all_cats:
            a = map_a.get(cat, 0)
            b = map_b.get(cat, 0)
            diff = a - b
            table_rows.append([cat, gbp(a), gbp(b), gbp(diff, show_sign=True)])

        total_a = sum(map_a.values())
        total_b = sum(map_b.values())
        table_rows.append(["**Total**", f"**{gbp(total_a)}**", f"**{gbp(total_b)}**", f"**{gbp(total_a - total_b, show_sign=True)}**"])

        output = f"# Spending Comparison: {period_label(period_a)} vs {period_label(period_b)}\n\n"
        output += md_table([
            "Category",
            period_label(period_a),
            period_label(period_b),
            "Difference",
        ], table_rows)

        return output

    except Exception as e:
        return f"Failed to compare spending: {e}"


@mcp.tool()
async def get_financial_health() -> str:
    """Get a comprehensive financial overview combining all data sources.

    Returns net worth, budget status, savings rate, FIRE progress, and
    business P&L in a single summary. Use for a full financial check-in.

    Use when Chris asks: "Full financial overview", "How am I doing financially?",
    "Financial health check"
    """
    try:
        sections = []

        # Net worth
        try:
            sections.append(await net_worth())
        except Exception as e:
            sections.append(f"_Net worth unavailable: {e}_")

        # Budget
        try:
            sections.append(await budget_status())
        except Exception as e:
            sections.append(f"_Budget unavailable: {e}_")

        # Savings rate
        try:
            sections.append(await savings_rate())
        except Exception as e:
            sections.append(f"_Savings rate unavailable: {e}_")

        # FIRE
        try:
            sections.append(await fire_status())
        except Exception as e:
            sections.append(f"_FIRE status unavailable: {e}_")

        # Business P&L (current month)
        try:
            sections.append(await business_pnl())
        except Exception as e:
            sections.append(f"_Business P&L unavailable: {e}_")

        return "\n\n---\n\n".join(sections)

    except Exception as e:
        return f"Failed to get financial health: {e}"


# =============================================================================
# SUBSCRIPTION MANAGEMENT TOOLS
# =============================================================================

@mcp.tool()
async def manage_subscription_add(
    name: str,
    amount: float,
    frequency: str = "monthly",
    scope: str = "personal",
    category: str | None = None,
    bank_description_pattern: str | None = None,
    payment_method: str | None = None,
    notes: str | None = None,
) -> str:
    """Add a new tracked subscription.

    Args:
        name: Subscription name (e.g. "Netflix", "Gousto")
        amount: Cost per billing period
        frequency: One of: weekly, fortnightly, monthly, quarterly, termly, annual
        scope: "personal" or "business"
        category: Category (e.g. "Streaming", "Food & Drink", "AI & Tech")
        bank_description_pattern: Text to match in bank transactions (for payment tracking)
        payment_method: How it's paid (e.g. "HSBC", "Monzo", "PayPal")
        notes: Optional notes

    Use when Chris says: "Add Gousto as a subscription", "Track my new gym membership",
    "That's a new subscription, add it"
    """
    try:
        return await _add_sub(
            name=name, amount=amount, frequency=frequency, scope=scope,
            category=category, bank_description_pattern=bank_description_pattern,
            payment_method=payment_method, notes=notes,
        )
    except Exception as e:
        return f"Failed to add subscription: {e}"


@mcp.tool()
async def manage_subscription_update(
    name: str,
    amount: float | None = None,
    status: str | None = None,
    frequency: str | None = None,
    notes: str | None = None,
) -> str:
    """Update an existing subscription (price, status, frequency, or notes).

    Finds the subscription by partial name match.

    Args:
        name: Subscription name or partial match (e.g. "Netflix", "piano")
        amount: New amount (if price changed)
        status: New status: "active", "paused", "cancelled", "trial"
        frequency: New frequency if billing cycle changed
        notes: Updated notes

    Use when Chris says: "Accept the Netflix price change", "Update piano to 259",
    "Pause my gym membership", "Council tax is actually annual"
    """
    try:
        return await _update_sub(name=name, amount=amount, status=status, frequency=frequency, notes=notes)
    except Exception as e:
        return f"Failed to update subscription: {e}"


@mcp.tool()
async def manage_subscription_cancel(name: str) -> str:
    """Mark a subscription as cancelled.

    Args:
        name: Subscription name or partial match

    Use when Chris says: "Cancel Netflix", "I've cancelled Disney+"
    """
    try:
        return await _cancel_sub(name)
    except Exception as e:
        return f"Failed to cancel subscription: {e}"


@mcp.tool()
async def manage_subscription_dismiss(
    description_pattern: str,
    reason: str | None = None,
) -> str:
    """Dismiss a false-positive recurring transaction alert.

    Adds the pattern to an exclusion list so the weekly subscription health
    check won't flag it again.

    Args:
        description_pattern: Bank transaction description to exclude
            (e.g. "DART CHARGE", "FORESTRY ENGLAND")
        reason: Why it's not a subscription (e.g. "toll road", "day trip")

    Use when Chris says: "Ignore Dart Charge, not a subscription",
    "Dismiss Forestry England", "That's not a sub"
    """
    try:
        return await _dismiss_alert(description_pattern, reason)
    except Exception as e:
        return f"Failed to dismiss alert: {e}"


@mcp.tool()
async def manage_subscription_list(
    scope: str | None = None,
    status: str | None = None,
) -> str:
    """List all tracked subscriptions with summary.

    Args:
        scope: Filter by "personal", "business", or None for all
        status: Filter by "active", "paused", "cancelled", "trial", or None for all

    Use when Chris asks: "List my subscriptions", "What subs am I paying for?",
    "Show me business subscriptions"
    """
    try:
        return await _list_subs(scope, status)
    except Exception as e:
        return f"Failed to list subscriptions: {e}"


if __name__ == "__main__":
    mcp.run()
