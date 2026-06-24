import { NextResponse } from "next/server";

const SUPABASE_URL = "https://modjoikyuhqzouxvieua.supabase.co";
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_KEY || "";
const HB_VERCEL_URL = "https://hadley-bricks-inventory-management.vercel.app";
const HB_INTERNAL_KEY = process.env.HB_INTERNAL_KEY || "";
const SERVICE_USER_ID = "4b6e94b4-661c-4462-9d14-b21df7d51e5b";

const SB_HEADERS = {
  apikey: SUPABASE_SERVICE_KEY,
  Authorization: `Bearer ${SUPABASE_SERVICE_KEY}`,
  "Content-Type": "application/json",
};

async function sbQuery(path: string) {
  try {
    const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
      headers: SB_HEADERS,
      signal: AbortSignal.timeout(8000),
      cache: "no-store",
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

// ── Orders to Dispatch ──────────────────────────────────────────────

async function getOrdersToDispatch() {
  const now = new Date().toISOString();

  // Platform orders (Amazon, BrickLink, etc.)
  const platformOrders = await sbQuery(
    `platform_orders?select=id,platform_order_id,buyer_name,total,currency,dispatch_by,platform,status&status=in.(Paid,Processing)&dispatch_by=not.is.null&user_id=eq.${SERVICE_USER_ID}&order=dispatch_by.asc`
  );

  // eBay orders
  const ebayOrders = await sbQuery(
    `ebay_orders?select=id,ebay_order_id,buyer_username,order_payment_status,order_fulfilment_status,dispatch_by,pricing_summary&order_payment_status=eq.PAID&order_fulfilment_status=in.(NOT_STARTED,IN_PROGRESS)&dispatch_by=not.is.null&user_id=eq.${SERVICE_USER_ID}&order=dispatch_by.asc`
  );

  const groups: Record<string, { count: number; overdue: number; urgent: number }> = {};

  const twoHours = new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString();

  for (const o of platformOrders || []) {
    const p = o.platform || "Other";
    if (!groups[p]) groups[p] = { count: 0, overdue: 0, urgent: 0 };
    groups[p].count++;
    if (o.dispatch_by < now) groups[p].overdue++;
    else if (o.dispatch_by <= twoHours) groups[p].urgent++;
  }

  for (const o of ebayOrders || []) {
    if (!groups["eBay"]) groups["eBay"] = { count: 0, overdue: 0, urgent: 0 };
    groups["eBay"].count++;
    if (o.dispatch_by < now) groups["eBay"].overdue++;
    else if (o.dispatch_by <= twoHours) groups["eBay"].urgent++;
  }

  const totalOverdue = Object.values(groups).reduce((s, g) => s + g.overdue, 0);
  const totalUrgent = Object.values(groups).reduce((s, g) => s + g.urgent, 0);
  const totalOrders = Object.values(groups).reduce((s, g) => s + g.count, 0);

  return { platforms: groups, totalOrders, totalOverdue, totalUrgent };
}

// ── Weekly Metrics / Targets ────────────────────────────────────────

async function getWeeklyMetrics() {
  const today = new Date();
  const dayOfWeek = today.getDay();
  const mondayOffset = dayOfWeek === 0 ? 6 : dayOfWeek - 1;
  const monday = new Date(today);
  monday.setDate(today.getDate() - mondayOffset);
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);

  const weekStart = monday.toISOString().slice(0, 10);
  const weekEnd = sunday.toISOString().slice(0, 10);
  const todayStr = today.toISOString().slice(0, 10);

  // Config / targets
  const configs = await sbQuery(
    `workflow_config?select=target_ebay_listings,target_amazon_listings,target_bricklink_weekly_value,target_daily_listed_value,target_daily_sold_value&user_id=eq.${SERVICE_USER_ID}&limit=1`
  );
  const config = configs?.[0] || {};

  // Listed this week (inventory items with listing_date in range — no status filter)
  const listedItems = await sbQuery(
    `inventory_items?select=listing_value,listing_platform,listing_date&user_id=eq.${SERVICE_USER_ID}&listing_date=gte.${weekStart}&listing_date=lte.${weekEnd}`
  );

  // BrickLink uploads this week
  const blUploads = await sbQuery(
    `bricklink_uploads?select=selling_price,upload_date&user_id=eq.${SERVICE_USER_ID}&upload_date=gte.${weekStart}&upload_date=lte.${weekEnd}`
  );

  // Sold this week (platform_orders)
  const soldOrders = await sbQuery(
    `platform_orders?select=total,order_date&user_id=eq.${SERVICE_USER_ID}&order_date=gte.${weekStart}&order_date=lte.${weekEnd}&status=in.(Paid,Processing,Shipped,Completed)`
  );

  // eBay sold this week
  const ebaySold = await sbQuery(
    `ebay_orders?select=total_fee_basis_amount,creation_date&user_id=eq.${SERVICE_USER_ID}&creation_date=gte.${weekStart}T00:00:00&creation_date=lte.${weekEnd}T23:59:59&order_payment_status=eq.PAID`
  );

  let listedValue = 0;
  let ebayValue = 0;
  let amazonValue = 0;
  let blValue = 0;

  for (const item of listedItems || []) {
    const val = Number(item.listing_value) || 0;
    listedValue += val;
    if (item.listing_platform === "ebay") ebayValue += val;
    else if (item.listing_platform === "amazon") amazonValue += val;
    else if (item.listing_platform === "bricklink") blValue += val;
  }

  // Add bricklink_uploads to BL value and total listed
  for (const u of blUploads || []) {
    const val = Number(u.selling_price) || 0;
    blValue += val;
    listedValue += val;
  }

  let soldValue = 0;
  for (const o of soldOrders || []) {
    soldValue += Number(o.total) || 0;
  }
  for (const o of ebaySold || []) {
    soldValue += Number(o.total_fee_basis_amount) || 0;
  }

  return {
    listedValue: Math.round(listedValue * 100) / 100,
    soldValue: Math.round(soldValue * 100) / 100,
    blValue: Math.round(blValue * 100) / 100,
    ebayValue: Math.round(ebayValue * 100) / 100,
    amazonValue: Math.round(amazonValue * 100) / 100,
    targets: {
      ebayValue: config.target_ebay_listings || 735,
      amazonValue: config.target_amazon_listings || 1050,
      blWeeklyValue: config.target_bricklink_weekly_value || 350,
      dailyListedValue: config.target_daily_listed_value || 305,
      dailySoldValue: config.target_daily_sold_value || 250,
    },
  };
}

// ── Platform Sync Status ────────────────────────────────────────────

async function getSyncStatus() {
  const tables = [
    { table: "ebay_sync_log", label: "eBay" },
    { table: "amazon_sync_log", label: "Amazon" },
    { table: "bricklink_sync_log", label: "BrickLink" },
    { table: "paypal_sync_log", label: "PayPal" },
    { table: "monzo_sync_log", label: "Monzo" },
  ];

  const results = await Promise.all(
    tables.map(async ({ table, label }) => {
      const rows = await sbQuery(
        `${table}?select=sync_type,status,completed_at,error_message&user_id=eq.${SERVICE_USER_ID}&order=completed_at.desc&limit=3`
      );
      return { label, rows: rows || [] };
    })
  );

  const latest: Record<string, { status: string; completedAt: string | null; error: string | null }> = {};
  for (const { label, rows } of results) {
    if (rows.length === 0) continue;
    // Group by sync_type within each platform
    for (const s of rows) {
      const key = s.sync_type ? `${label} ${s.sync_type}` : label;
      if (!latest[key]) {
        latest[key] = {
          status: s.status,
          completedAt: s.completed_at,
          error: s.error_message,
        };
      }
    }
  }

  return latest;
}

// ── P&L Summary ─────────────────────────────────────────────────────

async function getPnlSummary() {
  const now = new Date();
  const thisMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const lastMonthDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const lastMonth = `${lastMonthDate.getFullYear()}-${String(lastMonthDate.getMonth() + 1).padStart(2, "0")}`;

  try {
    const res = await fetch(
      `${HB_VERCEL_URL}/api/reports/profit-loss?startMonth=${lastMonth}&endMonth=${thisMonth}`,
      {
        headers: { "x-api-key": HB_INTERNAL_KEY },
        signal: AbortSignal.timeout(15000),
        cache: "no-store",
      }
    );

    if (!res.ok) return null;
    const json = await res.json();
    const data = json.data;
    if (!data?.categoryTotals || !data?.grandTotal) return null;

    const ct = data.categoryTotals;
    const gt = data.grandTotal;

    const revenue = (month: string) => (ct["Income"]?.[month] || 0);
    const fees = (month: string) => Math.abs(ct["Selling Fees"]?.[month] || 0);
    const cogs = (month: string) => Math.abs(ct["Stock Purchase"]?.[month] || 0);
    const postage = (month: string) => Math.abs(ct["Packing & Postage"]?.[month] || 0);
    const bills = (month: string) => Math.abs(ct["Bills"]?.[month] || 0);
    const home = (month: string) => Math.abs(ct["Home Costs"]?.[month] || 0);
    const other = (month: string) => postage(month) + bills(month) + home(month);
    const profit = (month: string) => gt[month] || 0;

    return {
      thisMonth: {
        month: thisMonth,
        revenue: revenue(thisMonth),
        fees: fees(thisMonth),
        cogs: cogs(thisMonth),
        other: other(thisMonth),
        profit: profit(thisMonth),
      },
      lastMonth: {
        month: lastMonth,
        revenue: revenue(lastMonth),
        fees: fees(lastMonth),
        cogs: cogs(lastMonth),
        other: other(lastMonth),
        profit: profit(lastMonth),
      },
    };
  } catch {
    return null;
  }
}

// ── Main handler ────────────────────────────────────────────────────

export async function GET() {
  const [orders, metrics, sync, pnl] = await Promise.all([
    getOrdersToDispatch(),
    getWeeklyMetrics(),
    getSyncStatus(),
    getPnlSummary(),
  ]);

  return NextResponse.json({ orders, metrics, sync, pnl });
}
