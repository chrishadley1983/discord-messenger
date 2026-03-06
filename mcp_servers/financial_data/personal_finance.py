"""Personal finance queries — net worth, budgets, spending, FIRE, transactions.

All functions query the `finance` schema in Supabase.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

from .config import get_date_range, month_range
from .formatters import gbp, pct, change_str, md_table, safe_float
from .supabase_client import finance_query, finance_rpc


# ═══════════════════════════════════════════════════════════════════════════
# NET WORTH
# ═══════════════════════════════════════════════════════════════════════════

async def net_worth() -> str:
    """Calculate current net worth from all active accounts."""
    # 1. Fetch active accounts
    accounts = await finance_query("accounts", {
        "is_active": "eq.true",
        "select": "id,name,type,include_in_net_worth",
    }, paginate=True)

    if not accounts:
        return "No active accounts found."

    # 2. Get current balances via RPC
    account_ids = [a["id"] for a in accounts]
    balances = await finance_rpc("get_account_balances_with_snapshots", {
        "account_ids": account_ids,
    })

    balance_map = {b["account_id"]: safe_float(b["current_balance"]) for b in balances}
    snapshot_dates = {b["account_id"]: b.get("snapshot_date") for b in balances}

    # 3. Build per-account and per-type totals
    by_type: dict[str, float] = defaultdict(float)
    by_account: list[dict] = []
    total = 0.0

    for acc in accounts:
        if not acc.get("include_in_net_worth", True):
            continue
        bal = balance_map.get(acc["id"], 0.0)
        acc_type = acc.get("type", "other")
        by_type[acc_type] += bal
        total += bal
        by_account.append({"name": acc["name"], "type": acc_type, "balance": bal})

    # 4. Get previous month total from wealth_snapshots
    today = date.today()
    prev_m = today.month - 1 if today.month > 1 else 12
    prev_y = today.year if today.month > 1 else today.year - 1
    prev_end = date(prev_y, prev_m, 1).isoformat()

    snapshots = await finance_query("wealth_snapshots", {
        "date": f"lte.{prev_end}",
        "order": "date.desc,account_id",
        "limit": "500",
    })

    # Deduplicate: take first (most recent) snapshot per account
    seen: set[str] = set()
    prev_total = 0.0
    for s in snapshots:
        aid = s["account_id"]
        if aid not in seen:
            seen.add(aid)
            # Only include if account is in our active set with include_in_net_worth
            matching = [a for a in accounts if a["id"] == aid and a.get("include_in_net_worth", True)]
            if matching:
                prev_total += safe_float(s.get("balance"))

    # 5. Format output
    type_labels = {
        "current": "Current Accounts",
        "savings": "Savings",
        "investment": "Investments",
        "pension": "Pensions",
        "isa": "ISAs",
        "property": "Property",
        "credit": "Credit Cards",
        "other": "Other",
    }

    rows = []
    for t in ["current", "savings", "isa", "investment", "pension", "property", "credit", "other"]:
        if t in by_type:
            rows.append([type_labels.get(t, t), gbp(by_type[t])])

    # Determine most recent snapshot date across all accounts
    all_snap_dates = [d for d in snapshot_dates.values() if d]
    latest_snapshot = max(all_snap_dates) if all_snap_dates else None

    output = f"# Net Worth\n\n"
    output += f"**Total: {gbp(total)}**"
    if prev_total:
        output += f"  ({change_str(total, prev_total)} vs last month)"
    output += "\n"
    if latest_snapshot:
        output += f"_Based on account snapshots as of {latest_snapshot}_\n"
    output += "\n"
    output += md_table(["Type", "Balance"], rows)

    # Top accounts
    by_account.sort(key=lambda a: abs(a["balance"]), reverse=True)
    top = by_account[:10]
    if top:
        output += "\n\n### Top Accounts\n"
        acc_rows = [[a["name"], a["type"], gbp(a["balance"])] for a in top]
        output += md_table(["Account", "Type", "Balance"], acc_rows)

    return output


# ═══════════════════════════════════════════════════════════════════════════
# BUDGET STATUS
# ═══════════════════════════════════════════════════════════════════════════

async def budget_status(year: int | None = None, month: int | None = None) -> str:
    """Get budget vs actual comparison."""
    y = year or date.today().year
    m = month or date.today().month

    params: dict = {"p_year": y}
    if m:
        params["p_month"] = m

    rows = await finance_rpc("get_budget_vs_actual", params)

    if not rows:
        return f"No budget data for {y}-{m:02d}."

    # Group by income vs expense
    income_rows = [r for r in rows if r.get("is_income")]
    expense_rows = [r for r in rows if not r.get("is_income")]

    total_income_budget = sum(safe_float(r["budget_amount"]) for r in income_rows)
    total_income_actual = sum(safe_float(r["actual_amount"]) for r in income_rows)
    total_expense_budget = sum(safe_float(r["budget_amount"]) for r in expense_rows)
    total_expense_actual = sum(safe_float(r["actual_amount"]) for r in expense_rows)

    output = f"# Budget Status — {y}-{m:02d}\n\n"
    output += f"**Income:** {gbp(total_income_actual)} actual vs {gbp(total_income_budget)} budgeted\n"
    output += f"**Expenses:** {gbp(total_expense_actual)} actual vs {gbp(total_expense_budget)} budgeted\n\n"

    # Over/under budget categories
    over = [(r["category_name"], safe_float(r["variance"])) for r in expense_rows if safe_float(r["variance"]) < 0]
    under = [(r["category_name"], safe_float(r["variance"])) for r in expense_rows if safe_float(r["variance"]) > 0]

    over.sort(key=lambda x: x[1])
    under.sort(key=lambda x: x[1], reverse=True)

    if over:
        output += "### Over Budget\n"
        for name, var in over[:5]:
            output += f"- {name}: {gbp(abs(var))} over\n"

    if under:
        output += "\n### Under Budget\n"
        for name, var in under[:5]:
            output += f"- {name}: {gbp(var)} under\n"

    # Full breakdown table
    output += "\n### Full Breakdown\n"
    table_rows = []
    for r in rows:
        table_rows.append([
            r.get("category_name", ""),
            "Income" if r.get("is_income") else "Expense",
            gbp(safe_float(r["budget_amount"])),
            gbp(safe_float(r["actual_amount"])),
            gbp(safe_float(r["variance"]), show_sign=True),
        ])
    output += md_table(["Category", "Type", "Budget", "Actual", "Variance"], table_rows)

    return output


# ═══════════════════════════════════════════════════════════════════════════
# SPENDING BY CATEGORY
# ═══════════════════════════════════════════════════════════════════════════

async def spending_by_category(
    period: str = "this_month",
    category_name: str | None = None,
) -> str:
    """Get spending breakdown by category for a period."""
    start, end = get_date_range(period)

    # Get excluded category IDs
    excluded_cats = await finance_query("categories", {
        "exclude_from_totals": "eq.true",
        "select": "id",
    })
    excluded_ids = [c["id"] for c in excluded_cats]

    # Call RPC
    rows = await finance_rpc("get_spending_by_category", {
        "start_date": start,
        "end_date": end,
        "excluded_ids": excluded_ids,
    })

    if not rows:
        return f"No spending data for {period}."

    # Filter by category name if specified
    if category_name:
        rows = [r for r in rows if category_name.lower() in r.get("category_name", "").lower()]

    total = sum(safe_float(r["total_amount"]) for r in rows)

    # Sort by amount descending
    rows.sort(key=lambda r: safe_float(r["total_amount"]), reverse=True)

    from .formatters import period_label
    output = f"# Spending by Category — {period_label(period)}\n\n"
    output += f"**Total: {gbp(total)}**\n\n"

    table_rows = []
    for r in rows:
        amt = safe_float(r["total_amount"])
        pct_val = (amt / total * 100) if total else 0
        table_rows.append([
            r.get("category_name", "Unknown"),
            gbp(amt),
            pct(pct_val),
        ])

    output += md_table(["Category", "Amount", "% of Total"], table_rows)
    return output


# ═══════════════════════════════════════════════════════════════════════════
# SAVINGS RATE
# ═══════════════════════════════════════════════════════════════════════════

async def savings_rate(year: int | None = None, month: int | None = None) -> str:
    """Get savings rate for a period."""
    y = year or date.today().year
    m = month or date.today().month

    params: dict = {"p_year": y}
    if m:
        params["p_month"] = m

    rows = await finance_rpc("get_savings_rate", params)

    if not rows:
        return f"No savings data for {y}-{m:02d}."

    r = rows[0]
    inc_actual = safe_float(r.get("total_income_actual"))
    inc_budget = safe_float(r.get("total_income_budget"))
    exp_actual = safe_float(r.get("total_expense_actual"))
    exp_budget = safe_float(r.get("total_expense_budget"))
    sav_actual = safe_float(r.get("savings_actual"))
    sav_budget = safe_float(r.get("savings_budget"))
    rate_actual = safe_float(r.get("savings_rate_actual"))
    rate_budget = safe_float(r.get("savings_rate_budget"))

    output = f"# Savings Rate — {y}-{m:02d}\n\n"
    output += md_table(
        ["Metric", "Actual", "Budget"],
        [
            ["Income", gbp(inc_actual), gbp(inc_budget)],
            ["Expenses", gbp(exp_actual), gbp(exp_budget)],
            ["Savings", gbp(sav_actual), gbp(sav_budget)],
            ["**Savings Rate**", f"**{pct(rate_actual)}**", pct(rate_budget)],
        ],
    )

    if rate_actual >= rate_budget:
        output += f"\n\nOn track — saving {pct(rate_actual - rate_budget)} above target."
    else:
        output += f"\n\nBelow target by {pct(rate_budget - rate_actual)}."

    return output


# ═══════════════════════════════════════════════════════════════════════════
# FIRE STATUS
# ═══════════════════════════════════════════════════════════════════════════

async def fire_status(scenario_name: str | None = None) -> str:
    """Get FIRE (Financial Independence) status and projections."""
    # Get FIRE inputs
    inputs = await finance_query("fire_inputs", {"limit": "1", "order": "updated_at.desc"})
    if not inputs:
        return "No FIRE inputs configured."

    fi = inputs[0]
    annual_expenses = safe_float(fi.get("annual_expenses"))
    safe_withdrawal = safe_float(fi.get("safe_withdrawal_rate", 4)) / 100
    target = annual_expenses / safe_withdrawal if safe_withdrawal else 0

    # Get scenarios
    scenarios = await finance_query("fire_scenarios", {"order": "name.asc"}, paginate=True)

    # Get current portfolio value (sum of investment/ISA/pension accounts)
    accounts = await finance_query("accounts", {
        "is_active": "eq.true",
        "include_in_net_worth": "eq.true",
        "select": "id,type",
    }, paginate=True)

    inv_ids = [a["id"] for a in accounts if a.get("type") in ("investment", "isa", "pension")]

    portfolio = 0.0
    if inv_ids:
        balances = await finance_rpc("get_account_balances_with_snapshots", {"account_ids": inv_ids})
        portfolio = sum(safe_float(b["current_balance"]) for b in balances)

    progress = (portfolio / target * 100) if target else 0

    output = f"# FIRE Status\n\n"
    output += f"**Portfolio:** {gbp(portfolio)}\n"
    output += f"**Target (FI Number):** {gbp(target)}\n"
    output += f"**Progress:** {pct(progress)}\n"
    output += f"**Annual Expenses:** {gbp(annual_expenses)}\n"
    output += f"**SWR:** {pct(safe_float(fi.get('safe_withdrawal_rate', 4)))}\n\n"

    # Coast FI: amount that would grow to target by retirement age
    current_age = safe_float(fi.get("current_age", 42))
    retirement_age = safe_float(fi.get("retirement_age", 60))
    growth_rate = safe_float(fi.get("real_return_rate", 5)) / 100
    years_to_retire = retirement_age - current_age

    if years_to_retire > 0 and growth_rate > 0:
        coast_fi = target / ((1 + growth_rate) ** years_to_retire)
        output += f"**Coast FI Number:** {gbp(coast_fi)}"
        if portfolio >= coast_fi:
            output += " — **Reached!**\n"
        else:
            output += f" — {gbp(coast_fi - portfolio)} to go\n"

    # Years to FI projection (simple)
    monthly_savings = safe_float(fi.get("monthly_savings", 0))
    annual_savings = monthly_savings * 12
    if annual_savings > 0 and growth_rate > 0:
        # Iterative projection
        bal = portfolio
        years = 0
        while bal < target and years < 100:
            bal = bal * (1 + growth_rate) + annual_savings
            years += 1
        if years < 100:
            fi_year = date.today().year + years
            output += f"**Years to FI:** ~{years} (projected {fi_year})\n"

    # Scenarios table
    if scenarios:
        output += "\n### Scenarios\n"
        if scenario_name:
            scenarios = [s for s in scenarios if scenario_name.lower() in s.get("name", "").lower()]

        s_rows = []
        for s in scenarios:
            s_monthly = safe_float(s.get("monthly_savings", monthly_savings))
            s_growth = safe_float(s.get("real_return_rate", safe_float(fi.get("real_return_rate", 5)))) / 100
            s_annual = s_monthly * 12
            bal = portfolio
            yrs = 0
            while bal < target and yrs < 100:
                bal = bal * (1 + s_growth) + s_annual
                yrs += 1
            s_rows.append([
                s.get("name", ""),
                gbp(s_monthly) + "/mo",
                pct(s_growth * 100),
                f"~{yrs}y" if yrs < 100 else "100+",
            ])
        output += md_table(["Scenario", "Savings", "Growth", "Years to FI"], s_rows)

    return output


# ═══════════════════════════════════════════════════════════════════════════
# FIND RECURRING TRANSACTIONS
# ═══════════════════════════════════════════════════════════════════════════

async def find_recurring(min_occurrences: int = 3, months: int = 6) -> str:
    """Find recurring transactions (subscriptions, regular payments)."""
    today = date.today()
    start_m = today.month - months
    start_y = today.year
    while start_m < 1:
        start_m += 12
        start_y -= 1
    start = date(start_y, start_m, 1).isoformat()

    txns = await finance_query("transactions", {
        "date": f"gte.{start}",
        "amount": "lt.0",  # outgoing only
        "select": "description,amount,date",
        "order": "date.desc",
    }, paginate=True)

    if not txns:
        return "No transactions found."

    # Normalise descriptions and group
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in txns:
        desc = t.get("description", "").strip()
        # Normalise: lowercase, strip trailing digits/dates
        norm = re.sub(r"\s+\d{2,}[/-]\d{2,}.*$", "", desc.lower()).strip()
        norm = re.sub(r"\s+", " ", norm)
        if norm:
            groups[norm].append(t)

    # Filter by min occurrences
    recurring = [(desc, txs) for desc, txs in groups.items() if len(txs) >= min_occurrences]
    recurring.sort(key=lambda x: len(x[1]), reverse=True)

    if not recurring:
        return f"No recurring transactions found (min {min_occurrences} occurrences in {months} months)."

    output = f"# Recurring Transactions (last {months} months)\n\n"

    rows = []
    for desc, txs in recurring[:30]:
        avg = sum(safe_float(t["amount"]) for t in txs) / len(txs)
        latest = txs[0].get("date", "")
        rows.append([desc.title(), str(len(txs)), gbp(avg), latest])

    output += md_table(["Description", "Count", "Avg Amount", "Latest"], rows)
    return output


# ═══════════════════════════════════════════════════════════════════════════
# SEARCH TRANSACTIONS
# ═══════════════════════════════════════════════════════════════════════════

async def search_transactions(
    query: str,
    period: str = "this_year",
    limit: int = 50,
) -> str:
    """Search personal transactions by description."""
    start, end = get_date_range(period)

    txns = await finance_query("transactions", {
        "description": f"ilike.*{query}*",
        "date": f"gte.{start}",
        "and": f"(date.lte.{end})",
        "select": "date,description,amount,category:categories(name)",
        "order": "date.desc",
        "limit": str(limit),
    })

    if not txns:
        return f"No transactions matching '{query}'."

    from .formatters import period_label
    total = sum(safe_float(t["amount"]) for t in txns)
    output = f"# Transactions matching '{query}' — {period_label(period)}\n\n"
    output += f"**{len(txns)} transactions, total: {gbp(total)}**\n\n"

    rows = []
    for t in txns[:30]:
        cat = _extract_category(t)
        rows.append([
            t.get("date", ""),
            t.get("description", "")[:40],
            cat,
            gbp(safe_float(t["amount"])),
        ])

    output += md_table(["Date", "Description", "Category", "Amount"], rows)

    if len(txns) > 30:
        output += f"\n\n_Showing 30 of {len(txns)} results_"

    return output


# ═══════════════════════════════════════════════════════════════════════════
# TRANSACTIONS BY CATEGORY
# ═══════════════════════════════════════════════════════════════════════════

async def transactions_by_category(
    category_name: str,
    period: str = "this_year",
    limit: int = 50,
) -> str:
    """Get all transactions in a specific category."""
    start, end = get_date_range(period)

    # Find category ID(s) matching the name
    cats = await finance_query("categories", {
        "name": f"ilike.*{category_name}*",
        "select": "id,name",
    })

    if not cats:
        return f"No category matching '{category_name}'. Use get_spending_by_category to see available categories."

    cat_ids = [c["id"] for c in cats]
    cat_names = [c["name"] for c in cats]

    # Fetch transactions for those categories
    ids_str = ",".join(cat_ids)
    txns = await finance_query("transactions", {
        "category_id": f"in.({ids_str})",
        "date": f"gte.{start}",
        "and": f"(date.lte.{end})",
        "select": "date,description,amount,category:categories(name)",
        "order": "date.desc",
        "limit": str(limit),
    })

    if not txns:
        return f"No transactions in '{', '.join(cat_names)}' for this period."

    from .formatters import period_label
    total = sum(safe_float(t["amount"]) for t in txns)
    output = f"# {', '.join(cat_names)} — {period_label(period)}\n\n"
    output += f"**{len(txns)} transactions, total: {gbp(total)}**\n\n"

    rows = []
    for t in txns[:50]:
        cat = _extract_category(t)
        rows.append([
            t.get("date", ""),
            t.get("description", "")[:50],
            gbp(safe_float(t["amount"])),
        ])

    output += md_table(["Date", "Description", "Amount"], rows)

    if len(txns) > 50:
        output += f"\n\n_Showing 50 of {len(txns)} results_"

    return output


def _extract_category(t: dict) -> str:
    """Extract category name from a transaction with embedded category join."""
    cat = t.get("category")
    if isinstance(cat, dict):
        return cat.get("name", "")
    if isinstance(cat, list) and cat:
        return cat[0].get("name", "")
    return ""
