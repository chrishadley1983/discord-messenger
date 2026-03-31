# Financial Data — MCP Tools Reference

You have direct access to Chris's financial data via the `financial-data` MCP server.
Use these tools when Chris asks about money, budgets, savings, investing, FIRE, or the LEGO business.

| Question | Tool |
|----------|------|
| "What's my net worth?" | `get_net_worth` |
| "Am I on budget?" / "What did I overspend on?" | `get_budget_status(year?, month?)` |
| "How much on eating out?" / "Spending breakdown" | `get_spending_by_category(period?, category_name?)` |
| "What's my savings rate?" | `get_savings_rate(year?, month?)` |
| "When can I retire?" / "FIRE progress" | `get_fire_status(scenario_name?)` |
| "What subscriptions do I pay?" | `find_recurring_transactions(min_occurrences?, months?)` |
| "Find all Tesco transactions" | `search_transactions_tool(query, period?, limit?)` |
| "Show all takeaway transactions" | `get_transactions_by_category(category_name, period?, limit?)` |
| "How's the business doing?" / "P&L" | `get_business_pnl(start_month?, end_month?)` |
| "Amazon revenue this month" | `get_platform_revenue(platform?, period?)` |
| "Compare March vs February" | `compare_spending(period_a, period_b)` |
| "Full financial overview" | `get_financial_health()` |

**Period values:** `this_month`, `last_month`, `this_quarter`, `last_quarter`, `this_year`, `last_year`, `all_time`.

These return formatted markdown — present the data directly, don't summarise unless asked.
