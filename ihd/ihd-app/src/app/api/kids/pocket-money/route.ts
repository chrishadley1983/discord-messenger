import { NextRequest, NextResponse } from "next/server";
import { readFile, writeFile, mkdir } from "fs/promises";
import { join } from "path";
import { randomUUID } from "crypto";

const DATA_DIR = join(process.cwd(), ".data");
const PM_FILE = join(DATA_DIR, "pocket-money.json");

interface Transaction {
  id: string;
  amount: number; // pence, positive=credit, negative=debit
  category: string;
  description: string;
  date: string;
  source: string;
}

interface ChildData {
  balance: number;
  transactions: Transaction[];
}

interface PocketMoneyData {
  emmie: ChildData;
  max: ChildData;
}

const SEED: PocketMoneyData = {
  emmie: {
    balance: 3400,
    transactions: [{
      id: "seed-001",
      amount: 3400,
      category: "pocket_money",
      description: "Starting balance",
      date: "2026-03-11T00:00:00Z",
      source: "manual",
    }],
  },
  max: {
    balance: 3700,
    transactions: [{
      id: "seed-002",
      amount: 3700,
      category: "pocket_money",
      description: "Starting balance",
      date: "2026-03-11T00:00:00Z",
      source: "manual",
    }],
  },
};

async function loadData(): Promise<PocketMoneyData> {
  try {
    const raw = await readFile(PM_FILE, "utf-8");
    return JSON.parse(raw);
  } catch {
    return SEED;
  }
}

async function saveData(data: PocketMoneyData) {
  await mkdir(DATA_DIR, { recursive: true });
  await writeFile(PM_FILE, JSON.stringify(data, null, 2));
}

export async function GET() {
  const data = await loadData();
  return NextResponse.json({
    emmie: {
      balance: data.emmie.balance,
      transactions: data.emmie.transactions.slice(-50).reverse(),
    },
    max: {
      balance: data.max.balance,
      transactions: data.max.transactions.slice(-50).reverse(),
    },
  });
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { child, amount, category, description, source } = body;

    if (child !== "emmie" && child !== "max") {
      return NextResponse.json({ error: "Invalid child" }, { status: 400 });
    }
    if (typeof amount !== "number" || amount === 0) {
      return NextResponse.json({ error: "Invalid amount" }, { status: 400 });
    }

    const data = await loadData();
    const childData = data[child as "emmie" | "max"];

    const tx: Transaction = {
      id: randomUUID(),
      amount,
      category: category || "pocket_money",
      description: description || "",
      date: new Date().toISOString(),
      source: source || "manual",
    };

    childData.transactions.push(tx);
    childData.balance += amount;

    await saveData(data);

    return NextResponse.json({ ok: true, balance: childData.balance });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
