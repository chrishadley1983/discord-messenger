"""Business finance queries — Hadley Bricks P&L and platform revenue.

Queries the `public` schema transaction tables in Supabase.
"""

from __future__ import annotations

import json
from datetime import date

from .config import (
    get_date_range,
    month_range,
    HB_INVENTORY_USER_ID,
    BRICKLINK_SALE_STATUSES,
    BRICKOWL_SALE_STATUSES,
)
from .formatters import gbp, pct, change_str, md_table, safe_float, period_label
from .supabase_client import public_query


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _user_filter() -> dict[str, str]:
    """Return user_id filter params if configured."""
    if HB_INVENTORY_USER_ID:
        return {"user_id": f"eq.{HB_INVENTORY_USER_ID}"}
    return {}


async def _ebay_revenue(start: str, end: str) -> dict:
    """Calculate eBay gross sales, refunds, and fees for a date range."""
    # Gross sales (SALE transactions, CREDIT booking)
    sales = await public_query("ebay_transactions", {
        **_user_filter(),
        "transaction_type": "eq.SALE",
        "booking_entry": "eq.CREDIT",
        "transaction_date": f"gte.{start}",
        "and": f"(transaction_date.lte.{end})",
        "select": "gross_transaction_amount,total_fee_amount",
    }, paginate=True)

    gross = sum(safe_float(t.get("gross_transaction_amount")) for t in sales)
    fees_from_sales = sum(safe_float(t.get("total_fee_amount")) for t in sales)

    # Refunds
    refunds = await public_query("ebay_transactions", {
        **_user_filter(),
        "transaction_type": "eq.REFUND",
        "booking_entry": "eq.DEBIT",
        "transaction_date": f"gte.{start}",
        "and": f"(transaction_date.lte.{end})",
        "select": "amount",
    }, paginate=True)

    refund_total = sum(safe_float(t.get("amount")) for t in refunds)

    # Non-sale charges (insertion fees, ad fees, shop fees, etc.)
    charges = await public_query("ebay_transactions", {
        **_user_filter(),
        "transaction_type": "eq.NON_SALE_CHARGE",
        "booking_entry": "eq.DEBIT",
        "transaction_date": f"gte.{start}",
        "and": f"(transaction_date.lte.{end})",
        "select": "amount",
    }, paginate=True)

    non_sale_fees = sum(safe_float(t.get("amount")) for t in charges)

    return {
        "gross": gross,
        "refunds": refund_total,
        "fees": abs(fees_from_sales) + abs(non_sale_fees),
        "net": gross - refund_total - abs(fees_from_sales) - abs(non_sale_fees),
    }


async def _amazon_revenue(start: str, end: str) -> dict:
    """Calculate Amazon revenue, refunds, and fees."""
    # Sales (Shipment transactions)
    sales = await public_query("amazon_transactions", {
        **_user_filter(),
        "transaction_type": "eq.Shipment",
        "posted_date": f"gte.{start}",
        "and": f"(posted_date.lte.{end})",
        "select": "gross_sales_amount,total_fees,total_amount",
    }, paginate=True)

    gross = sum(safe_float(t.get("gross_sales_amount")) for t in sales)
    fees = sum(abs(safe_float(t.get("total_fees"))) for t in sales)
    net_settlements = sum(safe_float(t.get("total_amount")) for t in sales)

    # Refunds
    refunds = await public_query("amazon_transactions", {
        **_user_filter(),
        "transaction_type": "in.(Refund,GuaranteeClaimRefund)",
        "posted_date": f"gte.{start}",
        "and": f"(posted_date.lte.{end})",
        "select": "total_amount",
    }, paginate=True)

    refund_total = sum(abs(safe_float(t.get("total_amount"))) for t in refunds)

    # Service fees (Amazon subscription etc.)
    service = await public_query("amazon_transactions", {
        **_user_filter(),
        "transaction_type": "eq.ServiceFee",
        "posted_date": f"gte.{start}",
        "and": f"(posted_date.lte.{end})",
        "select": "total_amount",
    }, paginate=True)

    service_fees = sum(abs(safe_float(t.get("total_amount"))) for t in service)

    return {
        "gross": gross,
        "refunds": refund_total,
        "fees": fees + service_fees,
        "net": gross - refund_total - fees - service_fees,
    }


async def _bricklink_revenue(start: str, end: str) -> dict:
    """Calculate BrickLink revenue."""
    statuses = ",".join(BRICKLINK_SALE_STATUSES)
    orders = await public_query("bricklink_transactions", {
        **_user_filter(),
        "order_status": f"in.({statuses})",
        "order_date": f"gte.{start}",
        "and": f"(order_date.lte.{end})",
        "select": "base_grand_total",
    }, paginate=True)

    gross = sum(safe_float(o.get("base_grand_total")) for o in orders)
    return {"gross": gross, "refunds": 0, "fees": 0, "net": gross}


async def _brickowl_revenue(start: str, end: str) -> dict:
    """Calculate Brick Owl revenue."""
    statuses = ",".join(BRICKOWL_SALE_STATUSES)
    orders = await public_query("brickowl_transactions", {
        **_user_filter(),
        "order_status": f"in.({statuses})",
        "order_date": f"gte.{start}",
        "and": f"(order_date.lte.{end})",
        "select": "base_grand_total",
    }, paginate=True)

    gross = sum(safe_float(o.get("base_grand_total")) for o in orders)
    return {"gross": gross, "refunds": 0, "fees": 0, "net": gross}


async def _stock_costs(start: str, end: str) -> float:
    """Calculate stock purchase costs from Monzo transactions."""
    # Monzo categories for stock: "Lego Stock", "Lego Parts"
    txns = await public_query("monzo_transactions", {
        **_user_filter(),
        "local_category": "in.(Lego Stock,Lego Parts)",
        "created": f"gte.{start}",
        "and": f"(created.lte.{end})",
        "select": "local_amount",
    }, paginate=True)

    return sum(abs(safe_float(t.get("local_amount"))) for t in txns)


async def _postage_packing_costs(start: str, end: str) -> dict:
    """Calculate postage and packing costs."""
    txns = await public_query("monzo_transactions", {
        **_user_filter(),
        "local_category": "in.(Postage,Packing Materials)",
        "created": f"gte.{start}",
        "and": f"(created.lte.{end})",
        "select": "local_amount,local_category",
    }, paginate=True)

    postage = sum(abs(safe_float(t.get("local_amount"))) for t in txns if t.get("local_category") == "Postage")
    packing = sum(abs(safe_float(t.get("local_amount"))) for t in txns if t.get("local_category") == "Packing Materials")
    return {"postage": postage, "packing": packing}


async def _other_costs(start: str, end: str) -> dict:
    """Calculate other business costs (services, software, office, selling fees)."""
    txns = await public_query("monzo_transactions", {
        **_user_filter(),
        "local_category": "in.(Services,Software,Office Space,Selling Fees)",
        "created": f"gte.{start}",
        "and": f"(created.lte.{end})",
        "select": "local_amount,local_category",
    }, paginate=True)

    cats: dict[str, float] = {}
    for t in txns:
        cat = t.get("local_category", "Other")
        cats[cat] = cats.get(cat, 0) + abs(safe_float(t.get("local_amount")))
    return cats


async def _mileage_costs(start: str, end: str) -> float:
    """Calculate mileage expense claims."""
    rows = await public_query("mileage_tracking", {
        **_user_filter(),
        "tracking_date": f"gte.{start}",
        "and": f"(tracking_date.lte.{end})",
        "select": "amount_claimed",
    }, paginate=True)

    return sum(safe_float(r.get("amount_claimed")) for r in rows)


async def _home_costs(start: str, end: str) -> dict:
    """Calculate home costs (Use of Home HMRC rates, Phone & Broadband, Insurance)."""
    costs = await public_query("home_costs", {
        **_user_filter(),
        "select": "cost_type,hours_per_month,monthly_cost,business_percent,annual_premium,business_stock_value,total_contents_value,start_date,end_date",
    }, paginate=True)

    # Parse date range for month counting
    from datetime import date as d
    s = d.fromisoformat(start)
    e = d.fromisoformat(end)

    use_of_home = 0.0
    phone_broadband = 0.0
    insurance = 0.0

    for c in costs:
        ct = c.get("cost_type", "")
        # Check if cost overlaps with our date range
        c_start = d.fromisoformat(c["start_date"]) if c.get("start_date") else s
        c_end = d.fromisoformat(c["end_date"]) if c.get("end_date") else e

        # Count overlapping months
        overlap_start = max(s, c_start)
        overlap_end = min(e, c_end)
        if overlap_start > overlap_end:
            continue

        # Rough month count
        months = max(1, (overlap_end.year - overlap_start.year) * 12 + overlap_end.month - overlap_start.month + 1)

        if ct == "use_of_home":
            hours = safe_float(c.get("hours_per_month"))
            if hours >= 101:
                monthly = 26.0
            elif hours >= 51:
                monthly = 18.0
            elif hours >= 25:
                monthly = 10.0
            else:
                monthly = 0.0
            use_of_home += monthly * months

        elif ct == "phone_broadband":
            mc = safe_float(c.get("monthly_cost"))
            bp = safe_float(c.get("business_percent"))
            phone_broadband += mc * (bp / 100) * months

        elif ct == "insurance":
            annual = safe_float(c.get("annual_premium"))
            stock = safe_float(c.get("business_stock_value"))
            contents = safe_float(c.get("total_contents_value"))
            if contents > 0:
                insurance += (annual * (stock / contents) / 12) * months

    return {
        "use_of_home": use_of_home,
        "phone_broadband": phone_broadband,
        "insurance": insurance,
    }


# ═══════════════════════════════════════════════════════════════════════════
# BUSINESS P&L
# ═══════════════════════════════════════════════════════════════════════════

async def business_pnl(
    start_month: str | None = None,
    end_month: str | None = None,
) -> str:
    """Generate Hadley Bricks P&L for a date range.

    Args:
        start_month: Start month as YYYY-MM (default: first of current month)
        end_month: End month as YYYY-MM (default: current month)
    """
    today = date.today()
    if start_month:
        parts = start_month.split("-")
        start = date(int(parts[0]), int(parts[1]), 1).isoformat()
    else:
        start = date(today.year, today.month, 1).isoformat()

    if end_month:
        parts = end_month.split("-")
        y, m = int(parts[0]), int(parts[1])
        import calendar
        end = date(y, m, calendar.monthrange(y, m)[1]).isoformat()
    else:
        end = today.isoformat()

    # Fetch all revenue streams in parallel-ish (sequential for simplicity)
    ebay = await _ebay_revenue(start, end)
    amazon = await _amazon_revenue(start, end)
    bricklink = await _bricklink_revenue(start, end)
    brickowl = await _brickowl_revenue(start, end)

    total_gross = ebay["gross"] + amazon["gross"] + bricklink["gross"] + brickowl["gross"]
    total_refunds = ebay["refunds"] + amazon["refunds"]
    total_fees = ebay["fees"] + amazon["fees"]
    net_revenue = total_gross - total_refunds - total_fees

    # Costs
    stock = await _stock_costs(start, end)
    pp = await _postage_packing_costs(start, end)
    other = await _other_costs(start, end)
    mileage = await _mileage_costs(start, end)
    home = await _home_costs(start, end)

    total_costs = (
        stock + pp["postage"] + pp["packing"] +
        sum(other.values()) + mileage +
        home["use_of_home"] + home["phone_broadband"] + home["insurance"]
    )

    net_profit = net_revenue - total_costs
    margin = (net_profit / net_revenue * 100) if net_revenue else 0

    # Format
    output = f"# Hadley Bricks P&L — {start} to {end}\n\n"

    # Revenue section
    output += "## Revenue\n"
    rev_rows = [
        ["eBay Gross", gbp(ebay["gross"])],
        ["eBay Refunds", f"-{gbp(ebay['refunds'])}"],
        ["eBay Fees", f"-{gbp(ebay['fees'])}"],
        ["eBay Net", gbp(ebay["net"])],
        ["---", "---"],
        ["Amazon Gross", gbp(amazon["gross"])],
        ["Amazon Refunds", f"-{gbp(amazon['refunds'])}"],
        ["Amazon Fees", f"-{gbp(amazon['fees'])}"],
        ["Amazon Net", gbp(amazon["net"])],
        ["---", "---"],
        ["BrickLink", gbp(bricklink["gross"])],
        ["Brick Owl", gbp(brickowl["gross"])],
        ["---", "---"],
        ["**Net Revenue**", f"**{gbp(net_revenue)}**"],
    ]
    output += md_table(["Item", "Amount"], rev_rows)

    # Costs section
    output += "\n\n## Costs\n"
    cost_rows = [
        ["Stock Purchases", gbp(stock)],
        ["Postage", gbp(pp["postage"])],
        ["Packing Materials", gbp(pp["packing"])],
    ]
    for cat, amt in other.items():
        cost_rows.append([cat, gbp(amt)])
    cost_rows.append(["Mileage", gbp(mileage)])
    cost_rows.append(["Use of Home", gbp(home["use_of_home"])])
    cost_rows.append(["Phone & Broadband", gbp(home["phone_broadband"])])
    cost_rows.append(["Insurance", gbp(home["insurance"])])
    cost_rows.append(["---", "---"])
    cost_rows.append(["**Total Costs**", f"**{gbp(total_costs)}**"])
    output += md_table(["Item", "Amount"], cost_rows)

    # Summary
    output += f"\n\n## Summary\n"
    output += f"**Net Profit: {gbp(net_profit)}** ({pct(margin)} margin)\n"

    return output


# ═══════════════════════════════════════════════════════════════════════════
# PLATFORM REVENUE
# ═══════════════════════════════════════════════════════════════════════════

async def platform_revenue(
    platform: str | None = None,
    period: str = "this_month",
) -> str:
    """Get revenue breakdown by platform or for a specific platform."""
    start, end = get_date_range(period)

    platforms = {}
    if not platform or platform.lower() == "ebay":
        platforms["eBay"] = await _ebay_revenue(start, end)
    if not platform or platform.lower() == "amazon":
        platforms["Amazon"] = await _amazon_revenue(start, end)
    if not platform or platform.lower() == "bricklink":
        platforms["BrickLink"] = await _bricklink_revenue(start, end)
    if not platform or platform.lower() in ("brickowl", "brick owl"):
        platforms["Brick Owl"] = await _brickowl_revenue(start, end)

    output = f"# Platform Revenue — {period_label(period)}\n\n"

    rows = []
    total_gross = 0
    total_net = 0
    for name, data in platforms.items():
        rows.append([name, gbp(data["gross"]), gbp(data["refunds"]), gbp(data["fees"]), gbp(data["net"])])
        total_gross += data["gross"]
        total_net += data["net"]

    rows.append(["**Total**", f"**{gbp(total_gross)}**", "", "", f"**{gbp(total_net)}**"])

    output += md_table(["Platform", "Gross", "Refunds", "Fees", "Net"], rows)
    return output
