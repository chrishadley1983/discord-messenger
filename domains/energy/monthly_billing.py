"""
Monthly billing sync: queries Octopus Energy GraphQL API for
account balance, bill data, and direct debit adequacy.

Run monthly on the 1st via Peter bot.
"""
import json
import os
import sys
from datetime import date, datetime

import httpx
from supabase import create_client

from .config import (
    SUPABASE_URL, SUPABASE_KEY,
    OCTOPUS_API_KEY, OCTOPUS_GRAPHQL_URL, OCTOPUS_ACCOUNT,
    DISCORD_ENERGY_WEBHOOK,
)


def get_graphql_token() -> str:
    """Authenticate with GraphQL API and get JWT token."""
    mutation = """
    mutation {
        obtainKrakenToken(input: {APIKey: "%s"}) {
            token
        }
    }
    """ % OCTOPUS_API_KEY

    resp = httpx.post(
        OCTOPUS_GRAPHQL_URL,
        json={"query": mutation},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["data"]["obtainKrakenToken"]["token"]


def query_graphql(token: str, query: str) -> dict:
    """Execute a GraphQL query with auth token."""
    resp = httpx.post(
        OCTOPUS_GRAPHQL_URL,
        json={"query": query},
        headers={"Authorization": token},
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"  GraphQL error {resp.status_code}: {resp.text[:500]}")
    return resp.json()


def fetch_billing_data(token: str) -> dict:
    """Fetch account balance, bills, and payment adequacy."""
    query = """
    {
        viewer {
            accounts {
                ... on AccountType {
                    number
                    balance
                    bills(first: 3) {
                        edges {
                            node {
                                billType
                                issuedDate
                                fromDate
                                toDate
                            }
                        }
                    }
                    transactions(first: 5) {
                        edges {
                            node {
                                amount
                                postedDate
                                title
                                isCredit
                            }
                        }
                    }
                }
            }
        }
    }
    """
    return query_graphql(token, query)


def main():
    if not SUPABASE_KEY:
        print("ERROR: SUPABASE_SERVICE_ROLE_KEY not found")
        sys.exit(1)

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    today = date.today()
    billing_month = today.replace(day=1).isoformat()

    print(f"Monthly Billing Sync - {today}")

    # Get GraphQL token
    print("  Authenticating with GraphQL API...")
    token = get_graphql_token()

    # Fetch billing data
    print("  Fetching billing data...")
    result = fetch_billing_data(token)

    if "errors" in result:
        print(f"  GraphQL errors: {result['errors']}")
        sys.exit(1)

    accounts = result.get("data", {}).get("viewer", {}).get("accounts", [])
    if not accounts:
        print("  No accounts found")
        sys.exit(1)

    account = accounts[0]
    # Balance returned in pence (integer). Positive = credit.
    balance_pence = int(account.get("balance", 0))
    balance_gbp = balance_pence / 100

    # Extract last bill
    bills = account.get("bills", {}).get("edges", [])
    last_bill_amount = None
    last_bill_date = None
    if bills:
        last_bill = bills[0]["node"]
        last_bill_date = last_bill.get("issuedDate")

    # Extract last payment (DD) — amounts also in pence
    transactions = account.get("transactions", {}).get("edges", [])
    dd_amount_pence = None
    for txn in transactions:
        node = txn["node"]
        if "direct debit" in (node.get("title") or "").lower() and not node.get("isCredit"):
            dd_amount_pence = abs(int(node["amount"]))
            break

    print(f"  Account balance: GBP {balance_gbp:.2f}")
    print(f"  Last DD payment: GBP {dd_amount_pence / 100:.2f}" if dd_amount_pence else "  Last DD payment: unknown")

    # Store in Supabase
    row = {
        "billing_month": billing_month,
        "account_balance_pence": balance_pence,
        "last_bill_amount_pence": last_bill_amount,
        "last_bill_date": last_bill_date,
        "dd_amount_pence": dd_amount_pence,
        "dd_adequate": balance_pence > 0,
        "raw_response": json.dumps(result),
        "updated_at": datetime.now(tz=__import__("datetime").timezone.utc).isoformat(),
    }

    sb.table("energy_billing").upsert(row, on_conflict="billing_month").execute()
    print(f"  Stored billing data for {billing_month}")

    # Post to Discord
    lines = [f"**Monthly Energy Billing** \u2014 {today.strftime('%B %Y')}\n"]

    if balance_pence >= 0:
        lines.append(f"\U0001f4b0 Account balance: **\u00a3{balance_gbp:.2f} in credit**")
    else:
        lines.append(f"\u26a0\ufe0f Account balance: **\u00a3{abs(balance_gbp):.2f} in debit**")

    if dd_amount_pence:
        lines.append(f"\U0001f3e6 Direct debit: \u00a3{dd_amount_pence / 100:.2f}/month")

    if balance_pence < 0:
        lines.append("\n\u26a0\ufe0f **Your account is in debit - DD may need increasing**")

    message = "\n".join(lines)
    print(message.encode("ascii", errors="replace").decode())

    try:
        httpx.post(DISCORD_ENERGY_WEBHOOK, json={"content": message}, timeout=10)
        print("\nPosted billing summary to Discord #energy")
    except Exception as e:
        print(f"Discord webhook error: {e}")


if __name__ == "__main__":
    main()
