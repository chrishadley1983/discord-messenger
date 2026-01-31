"""API Usage domain configuration."""

CHANNEL_ID = 1465761699582972142  # #api-balances

BUDGET_ALERTS = {
    "daily_warning": 1.00,   # Warn if daily spend exceeds $1
    "monthly_budget": 20.00  # Monthly budget cap
}

SYSTEM_PROMPT = """You track Chris's AI API usage and costs.

## Your Job
1. Report usage when asked
2. Break down by model/project
3. Alert on unusual spend
4. Weekly summaries

## Tone
- Factual, numbers-focused
- Flag anomalies clearly
"""
