# Phase 8c Data Fetchers

Add these to `domains/peterbot/data_fetchers.py`:

```python
# ============================================================
# PHASE 8c: Finance Data Fetchers
# ============================================================

import os
import requests
from datetime import datetime, date
from typing import Dict, Any, List

from config import FINANCE_TRACKER_URL, FINANCE_TRACKER_KEY, CRYPTO_HOLDINGS


# === SUPABASE HELPER ===

def _supabase_query(table: str, params: dict = None) -> List[dict]:
    """Query Supabase Finance Tracker."""
    if not FINANCE_TRACKER_URL or not FINANCE_TRACKER_KEY:
        return []
    
    headers = {
        "apikey": FINANCE_TRACKER_KEY,
        "Authorization": f"Bearer {FINANCE_TRACKER_KEY}",
        "Content-Type": "application/json"
    }
    
    url = f"{FINANCE_TRACKER_URL}/rest/v1/{table}"
    if params:
        query_parts = [f"{k}={v}" for k, v in params.items()]
        url += "?" + "&".join(query_parts)
    
    response = requests.get(url, headers=headers)
    return response.json() if response.status_code == 200 else []


# === SPENDING SUMMARY ===

def get_spending_summary_data() -> Dict[str, Any]:
    """Fetch current month spending breakdown."""
    if not FINANCE_TRACKER_URL:
        return {"error": "Finance Tracker not configured"}
    
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    
    transactions = _supabase_query("transactions", {
        "select": "amount,date,category_id,categories(name,group_name)",
        "date": f"gte.{month_start}",
        "amount": "lt.0"
    })
    
    by_category = {}
    by_group = {}
    total = 0
    
    for t in transactions:
        amount = abs(float(t.get("amount", 0)))
        total += amount
        
        cat = t.get("categories", {})
        cat_name = cat.get("name", "Uncategorized")
        group_name = cat.get("group_name", "Other")
        
        by_category[cat_name] = by_category.get(cat_name, 0) + amount
        by_group[group_name] = by_group.get(group_name, 0) + amount
    
    return {
        "month": today.strftime("%B %Y"),
        "total": round(total, 2),
        "by_category": dict(sorted(by_category.items(), key=lambda x: x[1], reverse=True)[:10]),
        "by_group": dict(sorted(by_group.items(), key=lambda x: x[1], reverse=True)),
        "transaction_count": len(transactions),
        "fetched_at": datetime.now().isoformat()
    }


# === BUDGET CHECK ===

def get_budget_check_data() -> Dict[str, Any]:
    """Compare actual spending vs budgets."""
    if not FINANCE_TRACKER_URL:
        return {"error": "Finance Tracker not configured"}
    
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    
    budgets = _supabase_query("budgets", {
        "select": "amount,categories(name,group_name)",
        "year": f"eq.{today.year}",
        "month": f"eq.{today.month}"
    })
    
    transactions = _supabase_query("transactions", {
        "select": "amount,category_id,categories(name)",
        "date": f"gte.{month_start}",
        "amount": "lt.0"
    })
    
    spending = {}
    for t in transactions:
        cat_name = t.get("categories", {}).get("name", "Uncategorized")
        spending[cat_name] = spending.get(cat_name, 0) + abs(float(t.get("amount", 0)))
    
    comparisons = []
    total_budget = 0
    total_spent = 0
    
    for b in budgets:
        cat_name = b.get("categories", {}).get("name", "Unknown")
        budget_amount = float(b.get("amount", 0))
        spent_amount = spending.get(cat_name, 0)
        
        total_budget += budget_amount
        total_spent += spent_amount
        
        pct = (spent_amount / budget_amount * 100) if budget_amount > 0 else 0
        
        comparisons.append({
            "category": cat_name,
            "budget": round(budget_amount, 2),
            "spent": round(spent_amount, 2),
            "remaining": round(budget_amount - spent_amount, 2),
            "percent": round(pct, 1),
            "status": "over" if pct > 100 else "warning" if pct > 80 else "ok"
        })
    
    comparisons.sort(key=lambda x: x["percent"], reverse=True)
    
    # Projection
    days_elapsed = today.day
    daily_rate = total_spent / days_elapsed if days_elapsed > 0 else 0
    days_in_month = 30  # Approximate
    projected = daily_rate * days_in_month
    
    return {
        "month": today.strftime("%B %Y"),
        "day_of_month": days_elapsed,
        "total_budget": round(total_budget, 2),
        "total_spent": round(total_spent, 2),
        "projected_total": round(projected, 2),
        "comparisons": comparisons,
        "fetched_at": datetime.now().isoformat()
    }


# === ACCOUNT BALANCES ===

def get_account_balances_data() -> Dict[str, Any]:
    """Fetch latest balance for each account from Finance Tracker."""
    if not FINANCE_TRACKER_URL:
        return {"error": "Finance Tracker not configured"}
    
    accounts = _supabase_query("accounts", {
        "select": "id,name,type,provider,icon,include_in_net_worth",
        "is_active": "eq.true",
        "is_archived": "eq.false",
        "order": "type,sort_order"
    })
    
    snapshots = _supabase_query("wealth_snapshots", {
        "select": "account_id,balance,date",
        "order": "date.desc"
    })
    
    latest_by_account = {}
    for s in snapshots:
        acc_id = s.get("account_id")
        if acc_id not in latest_by_account:
            latest_by_account[acc_id] = s
    
    by_type = {}
    total = 0
    
    for acc in accounts:
        acc_id = acc.get("id")
        acc_type = acc.get("type", "other")
        
        snapshot = latest_by_account.get(acc_id, {})
        balance = float(snapshot.get("balance", 0))
        
        if acc.get("include_in_net_worth", True):
            total += balance
        
        if acc_type not in by_type:
            by_type[acc_type] = []
        
        by_type[acc_type].append({
            "name": acc.get("name"),
            "provider": acc.get("provider"),
            "balance": round(balance, 2),
            "snapshot_date": snapshot.get("date"),
            "icon": acc.get("icon")
        })
    
    return {
        "by_type": by_type,
        "total": round(total, 2),
        "account_count": len(accounts),
        "fetched_at": datetime.now().isoformat()
    }


# === NET WORTH ===

def get_net_worth_data() -> Dict[str, Any]:
    """Calculate total net worth with FIRE progress."""
    if not FINANCE_TRACKER_URL:
        return {"error": "Finance Tracker not configured"}
    
    balances = get_account_balances_data()
    if "error" in balances:
        return balances
    
    breakdown = {}
    for acc_type, accounts in balances.get("by_type", {}).items():
        type_total = sum(a["balance"] for a in accounts)
        breakdown[acc_type] = round(type_total, 2)
    
    total = balances.get("total", 0)
    
    # FIRE progress
    fire_params = _supabase_query("fire_parameters", {"limit": "1"})
    fire_progress = None
    
    if fire_params:
        fp = fire_params[0]
        annual_spend = float(fp.get("annual_spend", 0))
        withdrawal_rate = float(fp.get("withdrawal_rate", 4)) / 100
        target = annual_spend / withdrawal_rate if withdrawal_rate > 0 else 0
        
        fire_progress = {
            "target": round(target, 2),
            "current": round(total, 2),
            "percent": round(total / target * 100, 1) if target > 0 else 0,
            "remaining": round(target - total, 2)
        }
    
    return {
        "total": round(total, 2),
        "breakdown": breakdown,
        "fire_progress": fire_progress,
        "fetched_at": datetime.now().isoformat()
    }


# === CRYPTO (LIVE PRICES) ===

def get_crypto_data(holdings: dict = None) -> Dict[str, Any]:
    """Fetch live crypto prices from CoinGecko."""
    holdings = holdings or CRYPTO_HOLDINGS or {}
    
    if not holdings:
        return {"error": "No crypto holdings configured"}
    
    coin_ids = list(holdings.keys())
    
    try:
        response = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": ",".join(coin_ids),
                "vs_currencies": "gbp",
                "include_24hr_change": "true",
                "include_7d_change": "true"
            }
        )
        
        if response.status_code != 200:
            return {"error": f"CoinGecko API error: {response.status_code}"}
        
        prices = response.json()
        
    except Exception as e:
        return {"error": f"CoinGecko error: {str(e)}"}
    
    results = []
    total_value = 0
    
    for coin_id, holding in holdings.items():
        amount = holding.get("amount", 0)
        
        coin_data = prices.get(coin_id, {})
        price = coin_data.get("gbp", 0)
        change_24h = coin_data.get("gbp_24h_change", 0)
        change_7d = coin_data.get("gbp_7d_change", 0)
        
        value = price * amount
        total_value += value
        
        results.append({
            "coin_id": coin_id,
            "amount": amount,
            "price": round(price, 2),
            "value": round(value, 2),
            "change_24h": round(change_24h, 2) if change_24h else None,
            "change_7d": round(change_7d, 2) if change_7d else None
        })
    
    return {
        "holdings": results,
        "total_value": round(total_value, 2),
        "fetched_at": datetime.now().isoformat()
    }


# === REGISTER IN SKILL_DATA_FETCHERS ===

# Add to existing SKILL_DATA_FETCHERS dict:
#
# SKILL_DATA_FETCHERS = {
#     ... existing entries ...
#     
#     # Phase 8c
#     "spending-summary": get_spending_summary_data,
#     "budget-check": get_budget_check_data,
#     "account-balances": get_account_balances_data,
#     "net-worth": get_net_worth_data,
#     "crypto-check": get_crypto_data,
# }
```
