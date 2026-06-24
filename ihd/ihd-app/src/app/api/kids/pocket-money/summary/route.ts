import { NextResponse } from "next/server";
import { readFile } from "fs/promises";
import { join } from "path";

const PM_FILE = join(process.cwd(), ".data", "pocket-money.json");

function formatPence(pence: number): string {
  const pounds = Math.abs(pence) / 100;
  const sign = pence < 0 ? "-" : "";
  return `${sign}\u00a3${pounds.toFixed(2)}`;
}

export async function GET() {
  try {
    const raw = await readFile(PM_FILE, "utf-8");
    const data = JSON.parse(raw);

    const emmieBalance = data.emmie?.balance ?? 0;
    const maxBalance = data.max?.balance ?? 0;

    return NextResponse.json({
      summary: `Emmie has ${formatPence(emmieBalance)}, Max has ${formatPence(maxBalance)}`,
      emmie: { balance: emmieBalance, formatted: formatPence(emmieBalance) },
      max: { balance: maxBalance, formatted: formatPence(maxBalance) },
    });
  } catch {
    return NextResponse.json({
      summary: "Pocket money data not available yet",
      emmie: { balance: 0, formatted: "\u00a30.00" },
      max: { balance: 0, formatted: "\u00a30.00" },
    });
  }
}
