import { NextRequest, NextResponse } from 'next/server';
import { promises as fs } from 'fs';
import path from 'path';
import type { PetStore, PetState, PetAction, PetOwner } from '@/lib/types/pet';
import { DECAY_RATES, EVOLUTION_RULES, FOODS, SLEEP_START, SLEEP_END } from '@/lib/types/pet';

const DATA_DIR = path.join(process.cwd(), '.data');
const PETS_FILE = path.join(DATA_DIR, 'pets.json');
const POOP_INTERVAL_HOURS = 4;

function defaultStore(): PetStore {
  return { pets: { max: null, emmie: null } };
}

async function readStore(): Promise<PetStore> {
  try {
    const raw = await fs.readFile(PETS_FILE, 'utf-8');
    return JSON.parse(raw) as PetStore;
  } catch {
    return defaultStore();
  }
}

async function writeStore(store: PetStore): Promise<void> {
  await fs.mkdir(DATA_DIR, { recursive: true });
  await fs.writeFile(PETS_FILE, JSON.stringify(store, null, 2), 'utf-8');
}

function isSleeping(): boolean {
  const hour = new Date().getHours();
  return hour >= SLEEP_START || hour < SLEEP_END;
}

function clamp(value: number, min = 0, max = 100): number {
  return Math.max(min, Math.min(max, value));
}

function applyDecay(pet: PetState): PetState {
  const now = new Date();
  const last = new Date(pet.lastUpdated);
  const hoursElapsed = (now.getTime() - last.getTime()) / (1000 * 60 * 60);

  if (hoursElapsed < 0.01) return pet;

  const updated = { ...pet };
  updated.hunger = clamp(pet.hunger - DECAY_RATES.hunger * hoursElapsed);
  updated.happiness = clamp(pet.happiness - DECAY_RATES.happiness * hoursElapsed);
  updated.cleanliness = clamp(pet.cleanliness - DECAY_RATES.cleanliness * hoursElapsed);

  // Spawn poops
  const lastPoop = new Date(pet.lastPoopAt);
  const poopHours = (now.getTime() - lastPoop.getTime()) / (1000 * 60 * 60);
  const newPoops = Math.floor(poopHours / POOP_INTERVAL_HOURS);
  if (newPoops > 0) {
    updated.poopCount = pet.poopCount + newPoops;
    updated.lastPoopAt = new Date(lastPoop.getTime() + newPoops * POOP_INTERVAL_HOURS * 60 * 60 * 1000).toISOString();
  }

  updated.lastUpdated = now.toISOString();

  const avg = Math.round((updated.hunger + updated.happiness + updated.cleanliness) / 3);
  updated.careHistory = [...pet.careHistory, avg].slice(-50);

  return updated;
}

function checkEvolution(pet: PetState): PetState {
  const rule = EVOLUTION_RULES[pet.stage];
  if (!rule) return pet;

  const daysAlive = (Date.now() - new Date(pet.bornAt).getTime()) / (1000 * 60 * 60 * 24);
  const careAvg = pet.careHistory.length > 0
    ? pet.careHistory.reduce((a, b) => a + b, 0) / pet.careHistory.length
    : 0;

  if (daysAlive >= rule.daysRequired && careAvg >= rule.minCareAvg) {
    return { ...pet, stage: rule.nextStage };
  }
  return pet;
}

export async function GET() {
  try {
    const store = await readStore();

    for (const id of ['max', 'emmie'] as PetOwner[]) {
      if (store.pets[id]) {
        store.pets[id] = checkEvolution(applyDecay(store.pets[id]));
      }
    }

    await writeStore(store);

    return NextResponse.json({
      pets: store.pets,
      sleeping: isSleeping(),
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error('GET /api/pets error:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}

export async function PUT(request: NextRequest) {
  try {
    const body = await request.json() as PetStore;
    if (body.pets) {
      await writeStore(body);
      return NextResponse.json({ ok: true });
    }
    return NextResponse.json({ error: 'Invalid state' }, { status: 400 });
  } catch (error) {
    console.error('PUT /api/pets error:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json() as PetAction;
    const store = await readStore();

    if (body.action === 'create') {
      if (store.pets[body.petId]) {
        return NextResponse.json({ error: 'Pet already exists' }, { status: 400 });
      }

      const now = new Date().toISOString();
      const newPet: PetState = {
        id: body.petId,
        name: body.name,
        species: body.species,
        stage: 'baby',
        bornAt: now,
        lastUpdated: now,
        hunger: 80,
        happiness: 80,
        cleanliness: 100,
        poopCount: 0,
        lastPoopAt: now,
        careHistory: [87],
        accessories: [],
        equippedAccessories: [],
        roomTheme: 'default',
        unlockedBackgrounds: ['default'],
        gameScores: {},
        personalitySeed: Math.random(),
      };

      store.pets[body.petId] = newPet;
      await writeStore(store);
      return NextResponse.json({ pet: newPet }, { status: 201 });
    }

    const pet = store.pets[body.petId];
    if (!pet) {
      return NextResponse.json({ error: 'Pet not found' }, { status: 404 });
    }

    if (isSleeping() && body.action !== 'interact') {
      return NextResponse.json({
        error: 'Your pet is sleeping! Come back after 7am.',
        sleeping: true,
      }, { status: 400 });
    }

    let updated = applyDecay(pet);

    switch (body.action) {
      case 'feed': {
        const food = FOODS[body.foodId || 'apple'];
        const boost = food?.hungerBoost ?? 15;
        updated.hunger = clamp(updated.hunger + boost);
        break;
      }
      case 'pet':
        updated.happiness = clamp(updated.happiness + 10);
        break;
      case 'clean':
        updated.poopCount = 0;
        updated.cleanliness = clamp(updated.cleanliness + 20);
        break;
      case 'play_result': {
        const happinessBoost = Math.min(Math.floor(body.score / 10), 20);
        updated.happiness = clamp(updated.happiness + happinessBoost);
        const currentHigh = updated.gameScores[body.game] ?? 0;
        if (body.score > currentHigh) {
          updated.gameScores[body.game] = body.score;
        }
        break;
      }
      case 'equip':
        if (updated.accessories.includes(body.accessoryId) && !updated.equippedAccessories.includes(body.accessoryId)) {
          updated.equippedAccessories.push(body.accessoryId);
        }
        break;
      case 'unequip':
        updated.equippedAccessories = updated.equippedAccessories.filter(a => a !== body.accessoryId);
        break;
      case 'set_room':
        if (updated.unlockedBackgrounds.includes(body.roomTheme)) {
          updated.roomTheme = body.roomTheme;
        }
        break;
      case 'interact': {
        updated.happiness = clamp(updated.happiness + 8);
        const otherId: PetOwner = body.petId === 'max' ? 'emmie' : 'max';
        const otherPet = store.pets[otherId];
        if (otherPet) {
          const otherUpdated = applyDecay(otherPet);
          otherUpdated.happiness = clamp(otherUpdated.happiness + 8);
          store.pets[otherId] = checkEvolution(otherUpdated);
        }
        break;
      }
    }

    updated = checkEvolution(updated);
    store.pets[body.petId] = updated;
    await writeStore(store);

    return NextResponse.json({ pet: updated });
  } catch (error) {
    console.error('POST /api/pets error:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
