"""Consolidate all extracted places from agent outputs into one file."""
import json
import os

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def deduplicate(places):
    """Deduplicate by name+city, keeping the entry with the longest context."""
    seen = {}
    for p in places:
        key = (p.get('name', '').lower().strip(), p.get('city', '').lower().strip())
        if key not in seen or len(p.get('context', '')) > len(seen[key].get('context', '')):
            seen[key] = p
    return list(seen.values())

def main():
    all_places = []

    # Load persisted places (batches 8-11 + youtube)
    persisted_path = os.path.join(OUTPUT_DIR, 'persisted_places.json')
    if os.path.exists(persisted_path):
        persisted = load_json(persisted_path)
        print(f"Loaded {len(persisted)} from persisted_places.json")
        all_places.extend(persisted)

    # Load inline places (batches 0-3, 4-7, 12-15)
    inline_path = os.path.join(OUTPUT_DIR, 'inline_places.json')
    if os.path.exists(inline_path):
        inline = load_json(inline_path)
        print(f"Loaded {len(inline)} from inline_places.json")
        all_places.extend(inline)

    print(f"\nTotal before dedup: {len(all_places)}")

    # Deduplicate
    deduped = deduplicate(all_places)
    print(f"After dedup: {len(deduped)}")

    # Sort by city then type then name
    deduped.sort(key=lambda p: (p.get('city', ''), p.get('type', ''), p.get('name', '')))

    # Write final output
    output_path = os.path.join(OUTPUT_DIR, 'extracted_places.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(deduped, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(deduped)} places to {output_path}")

    # Stats
    types = {}
    cities = {}
    for p in deduped:
        t = p.get('type', 'unknown')
        c = p.get('city', 'unknown')
        types[t] = types.get(t, 0) + 1
        cities[c] = cities.get(c, 0) + 1

    print("\nBy type:")
    for t, count in sorted(types.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count}")

    print("\nBy city (top 20):")
    for c, count in sorted(cities.items(), key=lambda x: -x[1])[:20]:
        print(f"  {c}: {count}")

    # Cleanup temp files
    for tmp in ['persisted_places.json', 'inline_places.json']:
        tmp_path = os.path.join(OUTPUT_DIR, tmp)
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
            print(f"Cleaned up {tmp}")

if __name__ == '__main__':
    main()
