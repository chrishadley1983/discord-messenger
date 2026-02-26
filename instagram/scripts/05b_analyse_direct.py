"""
05b_analyse_direct.py — Analyse posts directly using text content.

Reads caption.txt, transcript.txt, and meta.json for each post and generates
analysis.json using text-based extraction heuristics.

This is the fallback for when Claude CLI can't be called (nested session).
"""

import json
import re
from pathlib import Path
from collections import defaultdict

INSTAGRAM_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = INSTAGRAM_DIR / "data"
DOWNLOADS_DIR = INSTAGRAM_DIR / "downloads"

MASTER_INDEX_PATH = DATA_DIR / "master_index.json"
PROGRESS_PATH = DATA_DIR / "progress.json"


def load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="latin-1").strip()
        except Exception:
            return ""
    except Exception:
        return ""


# ── Country/City Detection ────────────────────────────────────────

COUNTRY_KEYWORDS = {
    "Japan": ["japan", "tokyo", "kyoto", "osaka", "hiroshima", "nara", "hokkaido",
              "okinawa", "nagoya", "fukuoka", "sapporo", "kobe", "yokohama",
              "shibuya", "shinjuku", "asakusa", "akihabara", "ginza", "harajuku",
              "roppongi", "tsukiji", "senso-ji", "fushimi", "arashiyama",
              "japanese", "ramen", "sushi", "onsen", "shinkansen", "izakaya",
              "matcha", "sakura", "sumo", "geisha", "meiji", "udon", "tempura",
              "takoyaki", "okonomiyaki", "wagyu", "kaiseki", "ryokan",
              "dotonbori", "kanji", "nihon", "nippon", "fuji"],
    "South Korea": ["korea", "korean", "seoul", "busan", "jeju", "incheon",
                    "gangnam", "myeongdong", "hongdae", "itaewon", "namsan",
                    "kimchi", "bibimbap", "soju", "kbbq", "k-bbq", "korean bbq",
                    "hanok", "bulgogi", "tteokbokki", "jjigae"],
    "Thailand": ["thailand", "thai", "bangkok", "chiang mai", "phuket", "pattaya",
                 "krabi", "koh samui", "koh phangan", "pad thai", "tuk tuk",
                 "temple", "wat", "floating market", "khao san"],
    "Vietnam": ["vietnam", "vietnamese", "hanoi", "ho chi minh", "saigon", "hoi an",
                "da nang", "ha long", "pho", "banh mi", "bun cha"],
    "Italy": ["italy", "italian", "rome", "roma", "florence", "firenze", "venice",
              "venezia", "milan", "milano", "naples", "napoli", "amalfi", "positano",
              "tuscany", "sicily", "sardinia", "cinque terre", "colosseum",
              "vatican", "pizza", "pasta", "gelato", "trattoria", "espresso"],
    "France": ["france", "french", "paris", "lyon", "marseille", "nice", "bordeaux",
               "provence", "versailles", "eiffel", "louvre", "montmartre",
               "croissant", "baguette", "patisserie"],
    "Spain": ["spain", "spanish", "barcelona", "madrid", "seville", "sevilla",
              "valencia", "malaga", "ibiza", "mallorca", "tapas", "paella",
              "sangria", "flamenco", "sagrada"],
    "Portugal": ["portugal", "portuguese", "lisbon", "lisboa", "porto", "algarve",
                 "faro", "sintra", "pasteis", "pastel de nata"],
    "Greece": ["greece", "greek", "athens", "santorini", "mykonos", "crete",
               "rhodes", "corfu", "acropolis", "parthenon", "gyros", "souvlaki"],
    "Turkey": ["turkey", "turkish", "istanbul", "cappadocia", "antalya", "bodrum",
               "ephesus", "bazaar", "kebab", "baklava", "bosphorus"],
    "Morocco": ["morocco", "moroccan", "marrakech", "marrakesh", "fez", "fes",
                "casablanca", "chefchaouen", "medina", "souk", "tagine", "riad"],
    "Mexico": ["mexico", "mexican", "cancun", "tulum", "playa del carmen",
               "mexico city", "oaxaca", "taco", "tacos", "guacamole", "cenote"],
    "USA": ["usa", "america", "american", "new york", "nyc", "los angeles",
            "san francisco", "chicago", "miami", "las vegas", "hawaii",
            "manhattan", "brooklyn", "california", "texas", "florida"],
    "UK": ["uk", "united kingdom", "england", "london", "scotland", "edinburgh",
           "manchester", "birmingham", "bristol", "oxford", "cambridge",
           "cornwall", "bath", "cotswolds", "lake district", "british"],
    "Indonesia": ["indonesia", "indonesian", "bali", "jakarta", "ubud",
                  "lombok", "komodo", "seminyak", "nusa"],
    "Philippines": ["philippines", "filipino", "manila", "cebu", "palawan",
                    "boracay", "el nido", "siargao"],
    "India": ["india", "indian", "delhi", "mumbai", "goa", "jaipur", "agra",
              "rajasthan", "kerala", "varanasi", "taj mahal", "curry"],
    "Australia": ["australia", "australian", "sydney", "melbourne", "brisbane",
                  "perth", "gold coast", "great barrier reef", "uluru"],
    "Croatia": ["croatia", "croatian", "dubrovnik", "split", "zagreb", "hvar",
                "plitvice"],
    "Netherlands": ["netherlands", "dutch", "amsterdam", "rotterdam", "hague"],
    "Germany": ["germany", "german", "berlin", "munich", "münchen", "hamburg",
                "frankfurt", "bavaria", "oktoberfest", "bratwurst", "pretzel"],
    "Switzerland": ["switzerland", "swiss", "zurich", "zürich", "geneva", "bern",
                    "lucerne", "interlaken", "zermatt", "alps"],
    "Austria": ["austria", "austrian", "vienna", "wien", "salzburg", "innsbruck"],
    "Czech Republic": ["czech", "prague", "praha", "bohemia"],
    "Hungary": ["hungary", "hungarian", "budapest"],
    "Poland": ["poland", "polish", "warsaw", "krakow", "kraków", "gdansk"],
    "Egypt": ["egypt", "egyptian", "cairo", "luxor", "aswan", "pyramid",
              "pharaoh", "nile", "sphinx"],
    "Sri Lanka": ["sri lanka", "colombo", "kandy", "galle", "sigiriya"],
    "Maldives": ["maldives", "maldivian", "malé"],
    "Dubai": ["dubai", "uae", "abu dhabi", "emirates", "burj"],
    "Singapore": ["singapore", "singaporean", "marina bay", "sentosa",
                  "hawker", "changi"],
    "Malaysia": ["malaysia", "malaysian", "kuala lumpur", "langkawi", "penang"],
    "China": ["china", "chinese", "beijing", "shanghai", "hong kong",
              "great wall", "forbidden city", "xi'an"],
    "Taiwan": ["taiwan", "taiwanese", "taipei", "kaohsiung", "taichung",
               "night market", "bubble tea"],
    "Colombia": ["colombia", "colombian", "bogota", "medellin", "cartagena"],
    "Peru": ["peru", "peruvian", "lima", "cusco", "machu picchu"],
    "Argentina": ["argentina", "buenos aires", "patagonia"],
    "Brazil": ["brazil", "brazilian", "rio", "são paulo", "sao paulo"],
    "Cuba": ["cuba", "cuban", "havana"],
    "Costa Rica": ["costa rica"],
    "Iceland": ["iceland", "icelandic", "reykjavik", "northern lights",
                "blue lagoon", "geyser"],
    "Norway": ["norway", "norwegian", "oslo", "bergen", "fjord", "fjords",
               "tromsø", "lofoten"],
    "Sweden": ["sweden", "swedish", "stockholm", "gothenburg"],
    "Denmark": ["denmark", "danish", "copenhagen"],
    "Finland": ["finland", "finnish", "helsinki"],
    "Ireland": ["ireland", "irish", "dublin", "galway", "cork"],
    "Scotland": ["scotland", "scottish", "edinburgh", "glasgow", "highlands"],
    "New Zealand": ["new zealand", "auckland", "queenstown", "wellington",
                    "rotorua", "milford sound"],
    "Canada": ["canada", "canadian", "toronto", "vancouver", "montreal",
               "quebec", "banff", "niagara"],
    "Jordan": ["jordan", "jordanian", "amman", "petra", "dead sea", "wadi rum"],
    "Israel": ["israel", "tel aviv", "jerusalem"],
}

TRAVEL_CATEGORIES = {
    "food_and_drink": ["restaurant", "food", "eat", "eating", "meal", "dish",
                       "cuisine", "cafe", "coffee", "bar", "drink", "ramen",
                       "sushi", "pizza", "pasta", "street food", "market",
                       "bakery", "dessert", "brunch", "lunch", "dinner",
                       "breakfast", "snack", "tasting", "foodie", "delicious",
                       "yummy", "izakaya", "bistro", "diner", "pub",
                       "cocktail", "wine", "beer", "sake", "tea"],
    "sightseeing": ["temple", "shrine", "castle", "palace", "museum",
                    "monument", "landmark", "view", "viewpoint", "lookout",
                    "tower", "bridge", "gate", "garden", "park", "square",
                    "cathedral", "church", "mosque", "historic", "heritage",
                    "ruins", "architecture", "statue"],
    "nature": ["beach", "mountain", "lake", "river", "waterfall", "forest",
               "island", "volcano", "canyon", "cliff", "valley", "trail",
               "hike", "hiking", "trek", "national park", "sunset", "sunrise",
               "ocean", "sea", "coast", "landscape", "scenic"],
    "culture": ["festival", "tradition", "dance", "music", "art", "craft",
                "local", "ceremony", "market", "bazaar", "souk",
                "experience", "cultural", "authentic"],
    "accommodation": ["hotel", "hostel", "airbnb", "resort", "stay",
                      "ryokan", "guesthouse", "villa", "lodge", "cabin"],
    "transport": ["train", "bus", "metro", "subway", "taxi", "flight",
                  "airport", "ferry", "boat", "bike", "cycle", "scooter",
                  "shinkansen", "tuk tuk", "cable car"],
    "nightlife": ["nightlife", "club", "bar", "pub", "party", "dancing",
                  "rooftop", "night out", "karaoke"],
    "shopping": ["shop", "shopping", "store", "mall", "boutique", "souvenir",
                 "market", "vintage", "thrift"],
    "tips": ["tip", "tips", "guide", "hack", "save", "budget", "itinerary",
             "must do", "must see", "avoid", "mistake", "advice", "plan",
             "checklist", "packing", "how to", "things to do", "hidden gem",
             "underrated", "overrated", "worth it", "don't miss"],
}

# ── Recipe Detection ──────────────────────────────────────────────

CUISINE_KEYWORDS = {
    "Japanese": ["japanese", "japan", "ramen", "sushi", "miso", "teriyaki",
                 "tempura", "udon", "soba", "matcha", "tofu", "edamame",
                 "katsu", "gyoza", "onigiri", "mochi", "dashi"],
    "Korean": ["korean", "korea", "kimchi", "bibimbap", "bulgogi",
               "tteokbokki", "gochujang", "kbbq", "japchae", "banchan"],
    "Chinese": ["chinese", "china", "wok", "stir fry", "dim sum",
                "dumpling", "noodle", "szechuan", "sichuan", "cantonese",
                "kung pao", "chow mein", "fried rice"],
    "Thai": ["thai", "thailand", "pad thai", "curry", "coconut milk",
             "lemongrass", "galangal", "basil", "fish sauce", "som tam"],
    "Indian": ["indian", "india", "curry", "masala", "tikka", "naan",
               "biryani", "dal", "paneer", "tandoori", "chutney", "samosa",
               "chai", "turmeric", "garam masala"],
    "Italian": ["italian", "italy", "pasta", "pizza", "risotto", "gnocchi",
                "pesto", "bolognese", "carbonara", "lasagna", "tiramisu",
                "bruschetta", "focaccia", "prosciutto", "parmesan",
                "mozzarella", "ravioli", "marinara"],
    "Mexican": ["mexican", "mexico", "taco", "burrito", "enchilada",
                "quesadilla", "salsa", "guacamole", "tortilla", "chipotle",
                "jalapeño", "cilantro", "lime", "fajita", "nacho"],
    "Mediterranean": ["mediterranean", "hummus", "falafel", "pita",
                      "tahini", "olive oil", "greek", "za'atar", "halloumi",
                      "tabbouleh", "fattoush"],
    "Middle Eastern": ["middle eastern", "shawarma", "kebab", "labneh",
                       "sumac", "baba ganoush", "baklava", "kofte"],
    "American": ["american", "burger", "bbq", "barbecue", "mac and cheese",
                 "fried chicken", "hot dog", "pancake", "waffle"],
    "British": ["british", "english", "roast", "pie", "fish and chips",
                "scone", "crumpet", "full english", "yorkshire pudding"],
    "French": ["french", "france", "croissant", "baguette", "quiche",
               "crepe", "soufflé", "ratatouille", "coq au vin",
               "crème brûlée", "brioche"],
    "Vietnamese": ["vietnamese", "vietnam", "pho", "banh mi", "spring roll",
                   "bun", "nuoc mam"],
    "Fusion": ["fusion"],
    "Healthy/Clean": ["healthy", "clean eating", "protein", "macro",
                      "meal prep", "low calorie", "high protein",
                      "whole food", "nutritious", "balanced"],
    "Comfort Food": ["comfort food", "cozy", "warm", "hearty", "cheesy",
                     "loaded", "creamy", "rich"],
}

MEAL_TYPES = {
    "breakfast": ["breakfast", "brunch", "morning", "oatmeal", "porridge",
                  "eggs", "toast", "pancake", "waffle", "smoothie bowl",
                  "granola", "cereal", "yogurt bowl"],
    "lunch": ["lunch", "sandwich", "wrap", "salad", "bowl", "midday"],
    "dinner": ["dinner", "supper", "evening meal", "main course", "entree"],
    "snack": ["snack", "bite", "appetizer", "starter", "dip", "hummus",
              "chips", "popcorn", "energy ball", "protein ball"],
    "dessert": ["dessert", "sweet", "cake", "cookie", "brownie", "ice cream",
                "chocolate", "pastry", "pie", "tart", "pudding", "mochi",
                "tiramisu", "crème brûlée"],
    "drink": ["drink", "smoothie", "juice", "coffee", "latte", "tea",
              "cocktail", "mocktail", "shake", "matcha latte"],
}

# ── Body Area Detection (Stretching) ─────────────────────────────

BODY_AREAS = {
    "back": ["back", "spine", "spinal", "lumbar", "lower back", "upper back",
             "lat", "lats", "thoracic", "erector"],
    "hips": ["hip", "hips", "hip flexor", "hip opener", "glute", "glutes",
             "piriformis", "psoas", "groin", "adductor"],
    "hamstrings": ["hamstring", "hamstrings", "posterior chain", "back of leg"],
    "shoulders": ["shoulder", "shoulders", "rotator cuff", "deltoid", "trap",
                  "traps", "scapula"],
    "neck": ["neck", "cervical", "upper trap"],
    "quads": ["quad", "quads", "quadricep", "front of thigh", "knee"],
    "calves": ["calf", "calves", "achilles", "ankle", "shin"],
    "chest": ["chest", "pec", "pecs", "pectoral"],
    "arms": ["arm", "arms", "bicep", "tricep", "forearm", "wrist", "elbow"],
    "core": ["core", "abs", "abdominal", "oblique", "plank"],
    "full_body": ["full body", "whole body", "total body", "mobility",
                  "flexibility", "warm up", "cool down", "morning routine",
                  "daily stretch"],
}

# ── Life Hack Categories ─────────────────────────────────────────

HACK_CATEGORIES = {
    "cleaning": ["clean", "cleaning", "stain", "wash", "scrub", "mop",
                 "wipe", "disinfect", "organize", "declutter"],
    "cooking": ["cook", "cooking", "kitchen", "food", "recipe", "bake",
                "meal prep", "ingredient", "seasoning"],
    "health": ["health", "wellness", "sleep", "stress", "anxiety",
               "mental health", "energy", "immune", "gut", "inflammation",
               "vitamin", "supplement"],
    "productivity": ["productive", "productivity", "focus", "time",
                     "morning routine", "habit", "discipline", "goal",
                     "mindset", "motivation"],
    "tech": ["tech", "phone", "app", "iphone", "android", "computer",
             "wifi", "bluetooth", "setting", "feature", "shortcut"],
    "finance": ["money", "save", "saving", "budget", "invest", "financial",
                "credit", "debt", "income", "expense"],
    "organisation": ["organise", "organize", "organisation", "organization",
                     "storage", "space", "tidy", "sort", "label", "drawer",
                     "closet", "wardrobe", "pantry"],
    "diy": ["diy", "fix", "repair", "build", "make", "craft", "tool",
            "paint", "glue", "tape"],
}


def detect_keywords(text: str, keyword_dict: dict[str, list[str]]) -> str | None:
    """Find the best matching category from a keyword dict."""
    text_lower = text.lower()
    scores: dict[str, int] = defaultdict(int)
    for category, keywords in keyword_dict.items():
        for kw in keywords:
            if kw in text_lower:
                scores[category] += 1
    if scores:
        return max(scores, key=scores.get)
    return None


def detect_all_keywords(text: str, keyword_dict: dict[str, list[str]]) -> list[tuple[str, int]]:
    """Find all matching categories with scores, sorted by score descending."""
    text_lower = text.lower()
    scores: dict[str, int] = defaultdict(int)
    for category, keywords in keyword_dict.items():
        for kw in keywords:
            if kw in text_lower:
                scores[category] += 1
    return sorted(scores.items(), key=lambda x: -x[1])


def extract_city(text: str, country: str) -> str:
    """Try to extract a city/region from text for a given country."""
    text_lower = text.lower()

    # Country-specific city lists
    city_maps = {
        "Japan": {
            "Tokyo": ["tokyo", "shibuya", "shinjuku", "asakusa", "akihabara",
                       "ginza", "harajuku", "roppongi", "tsukiji", "ueno",
                       "ikebukuro", "shimokitazawa", "nakameguro"],
            "Kyoto": ["kyoto", "fushimi", "arashiyama", "gion", "kiyomizu",
                      "bamboo grove", "bamboo forest"],
            "Osaka": ["osaka", "dotonbori", "namba", "umeda", "shinsekai",
                      "kuromon"],
            "Hiroshima": ["hiroshima"],
            "Nara": ["nara"],
            "Hokkaido": ["hokkaido", "sapporo", "otaru", "niseko", "furano"],
            "Okinawa": ["okinawa"],
            "Nagoya": ["nagoya"],
            "Fukuoka": ["fukuoka", "hakata"],
            "Kobe": ["kobe"],
            "Yokohama": ["yokohama"],
            "Kamakura": ["kamakura"],
            "Hakone": ["hakone"],
            "Mt. Fuji": ["fuji", "mt fuji", "mount fuji"],
        },
        "South Korea": {
            "Seoul": ["seoul", "gangnam", "myeongdong", "hongdae", "itaewon",
                      "namsan", "insadong", "bukchon"],
            "Busan": ["busan"],
            "Jeju": ["jeju"],
            "Incheon": ["incheon"],
        },
        "Thailand": {
            "Bangkok": ["bangkok", "khao san"],
            "Chiang Mai": ["chiang mai"],
            "Phuket": ["phuket"],
        },
        "Italy": {
            "Rome": ["rome", "roma", "colosseum", "vatican", "trastevere"],
            "Florence": ["florence", "firenze"],
            "Venice": ["venice", "venezia"],
            "Amalfi Coast": ["amalfi", "positano", "ravello"],
            "Naples": ["naples", "napoli"],
            "Milan": ["milan", "milano"],
            "Cinque Terre": ["cinque terre"],
        },
    }

    cities = city_maps.get(country, {})
    for city, keywords in cities.items():
        for kw in keywords:
            if kw in text_lower:
                return city

    return "General"


def extract_hashtags(text: str) -> list[str]:
    return re.findall(r"#(\w+)", text)


def analyse_travel(caption: str, transcript: str, meta: dict, username: str, url: str) -> dict:
    combined = f"{caption} {transcript}"

    country = detect_keywords(combined, COUNTRY_KEYWORDS) or "Unknown"
    city = extract_city(combined, country)
    category = detect_keywords(combined, TRAVEL_CATEGORIES) or "sightseeing"

    # Try to extract specific location from caption
    location = meta.get("location", "") or ""

    # One-line summary from first sentence of caption
    caption_clean = re.sub(r"#\w+", "", caption).strip()
    summary = caption_clean.split(".")[0].split("!")[0].split("\n")[0].strip()
    if not summary or len(summary) < 5:
        summary = f"{category.replace('_', ' ').title()} in {city}, {country}"

    # Cost level guess
    cost_hints = combined.lower()
    if any(w in cost_hints for w in ["cheap", "budget", "free", "affordable", "street food"]):
        cost = "budget"
    elif any(w in cost_hints for w in ["luxury", "expensive", "fine dining", "michelin", "5 star"]):
        cost = "luxury"
    else:
        cost = "mid"

    confidence = "high" if country != "Unknown" else "low"
    if city == "General" and country != "Unknown":
        confidence = "medium"

    return {
        "country": country,
        "city_or_region": city,
        "specific_location": location if location else None,
        "category": category,
        "best_time_to_visit": None,
        "estimated_cost_level": cost,
        "one_line_summary": summary[:120],
        "source_username": f"@{username}",
        "source_url": url,
        "confidence": confidence,
        "notes": None,
    }


def analyse_recipe(caption: str, transcript: str, meta: dict, username: str, url: str) -> dict:
    combined = f"{caption} {transcript}"

    cuisine = detect_keywords(combined, CUISINE_KEYWORDS) or "Other"
    meal_type = detect_keywords(combined, MEAL_TYPES) or "dinner"

    # Extract dish name from caption first line
    caption_clean = re.sub(r"#\w+", "", caption).strip()
    first_line = caption_clean.split("\n")[0].strip()
    dish_name = first_line[:80] if first_line else "Untitled Recipe"

    # Try to find ingredients
    ingredients = []
    for line in (caption + "\n" + transcript).split("\n"):
        line = line.strip()
        if line.startswith("-") or line.startswith("•") or re.match(r"^\d+[\.\)]\s", line):
            ingredients.append(line.lstrip("-•0123456789.) "))

    # Method from transcript if available
    method = ""
    if transcript and "(no audio)" not in transcript and "(no speech)" not in transcript:
        # Use transcript as method summary (first 300 chars)
        clean_transcript = transcript.replace("[Language: en]\n", "").replace("[Language: ", "").strip()
        if len(clean_transcript) > 10:
            method = clean_transcript[:300]

    # Dietary tags
    tags = []
    combined_lower = combined.lower()
    if any(w in combined_lower for w in ["vegan", "plant based", "plant-based"]):
        tags.append("vegan")
    if any(w in combined_lower for w in ["vegetarian", "veggie", "meat-free", "meatless"]):
        tags.append("vegetarian")
    if any(w in combined_lower for w in ["gluten free", "gluten-free", "gf"]):
        tags.append("gluten_free")
    if any(w in combined_lower for w in ["dairy free", "dairy-free"]):
        tags.append("dairy_free")
    if any(w in combined_lower for w in ["keto", "low carb", "low-carb"]):
        tags.append("keto")
    if any(w in combined_lower for w in ["high protein", "protein"]):
        tags.append("high_protein")

    # Difficulty
    if any(w in combined_lower for w in ["easy", "simple", "quick", "5 minute", "10 minute", "beginner"]):
        difficulty = "easy"
    elif any(w in combined_lower for w in ["hard", "complex", "advanced", "technique"]):
        difficulty = "hard"
    else:
        difficulty = "medium"

    return {
        "dish_name": dish_name,
        "cuisine_type": cuisine,
        "meal_type": meal_type,
        "ingredients_visible": ingredients[:15] if ingredients else None,
        "method_summary": method if method else None,
        "dietary_tags": tags if tags else None,
        "difficulty": difficulty,
        "prep_time_estimate": None,
        "source_username": f"@{username}",
        "source_url": url,
        "confidence": "medium",
        "notes": None,
    }


def analyse_stretching(caption: str, transcript: str, meta: dict, username: str, url: str) -> dict:
    combined = f"{caption} {transcript}"

    body_area = detect_keywords(combined, BODY_AREAS) or "full_body"

    caption_clean = re.sub(r"#\w+", "", caption).strip()
    first_line = caption_clean.split("\n")[0].strip()
    exercise_name = first_line[:80] if first_line else "Stretch Exercise"

    # Instructions from transcript
    instructions = ""
    if transcript and "(no audio)" not in transcript and "(no speech)" not in transcript:
        clean = transcript.replace("[Language: en]\n", "").strip()
        if len(clean) > 10:
            instructions = clean[:400]

    # Duration/reps
    duration = None
    dur_match = re.search(r"(\d+)\s*(seconds?|secs?|minutes?|mins?|reps?|sets?)", combined.lower())
    if dur_match:
        duration = dur_match.group(0)

    # Equipment
    equipment = "none"
    combined_lower = combined.lower()
    if any(w in combined_lower for w in ["foam roller", "roller"]):
        equipment = "foam_roller"
    elif any(w in combined_lower for w in ["band", "resistance band"]):
        equipment = "band"
    elif any(w in combined_lower for w in ["block", "yoga block"]):
        equipment = "block"
    elif any(w in combined_lower for w in ["wall"]):
        equipment = "wall"

    if any(w in combined_lower for w in ["beginner", "easy", "gentle"]):
        difficulty = "beginner"
    elif any(w in combined_lower for w in ["advanced", "hard", "intense"]):
        difficulty = "advanced"
    else:
        difficulty = "intermediate"

    return {
        "exercise_name": exercise_name,
        "body_area": body_area,
        "duration_or_reps": duration,
        "instructions_summary": instructions if instructions else None,
        "equipment_needed": equipment,
        "difficulty": difficulty,
        "source_username": f"@{username}",
        "source_url": url,
        "confidence": "medium",
        "notes": None,
    }


def analyse_life_hack(caption: str, transcript: str, meta: dict, username: str, url: str) -> dict:
    combined = f"{caption} {transcript}"

    category = detect_keywords(combined, HACK_CATEGORIES) or "other"

    caption_clean = re.sub(r"#\w+", "", caption).strip()
    first_line = caption_clean.split("\n")[0].strip()
    hack_title = first_line[:80] if first_line else "Life Hack"

    # Description from caption
    lines = caption_clean.split("\n")
    desc = " ".join(l.strip() for l in lines[:3] if l.strip())[:200]

    # Steps from transcript
    steps = ""
    if transcript and "(no audio)" not in transcript and "(no speech)" not in transcript:
        clean = transcript.replace("[Language: en]\n", "").strip()
        if len(clean) > 10:
            steps = clean[:400]

    return {
        "hack_title": hack_title,
        "category": category,
        "description": desc if desc else None,
        "steps": steps if steps else None,
        "items_needed": None,
        "source_username": f"@{username}",
        "source_url": url,
        "confidence": "medium",
        "notes": None,
    }


def analyse_uncollected(caption: str, transcript: str, meta: dict, username: str, url: str) -> dict:
    combined = f"{caption} {transcript}"

    # Guess collection
    travel_score = len(detect_all_keywords(combined, COUNTRY_KEYWORDS))
    recipe_score = len(detect_all_keywords(combined, CUISINE_KEYWORDS))
    stretch_score = len(detect_all_keywords(combined, BODY_AREAS))
    hack_score = len(detect_all_keywords(combined, HACK_CATEGORIES))

    scores = {
        "Travel": travel_score,
        "Recipes": recipe_score,
        "Stretching": stretch_score,
        "Life Hacks": hack_score,
    }
    best = max(scores, key=scores.get) if any(scores.values()) else "Other"
    if best != "Other" and scores.get(best, 0) == 0:
        best = "Other"

    # Generate analysis based on best guess
    if best == "Travel":
        base = analyse_travel(caption, transcript, meta, username, url)
    elif best == "Recipes":
        base = analyse_recipe(caption, transcript, meta, username, url)
    elif best == "Stretching":
        base = analyse_stretching(caption, transcript, meta, username, url)
    elif best == "Life Hacks":
        base = analyse_life_hack(caption, transcript, meta, username, url)
    else:
        caption_clean = re.sub(r"#\w+", "", caption).strip()
        first_line = caption_clean.split("\n")[0].strip()[:80]
        base = {
            "one_line_summary": first_line or "Uncategorised post",
            "source_username": f"@{username}",
            "source_url": url,
            "confidence": "low",
            "notes": "Could not classify into any collection",
        }

    base["best_guess_collection"] = best
    base["reasoning"] = f"Keyword matching scored: {dict(scores)}"
    if base.get("confidence") != "low":
        base["confidence"] = "medium" if scores.get(best, 0) > 1 else "low"

    return base


def main():
    master_index = load_json(MASTER_INDEX_PATH)
    progress = load_json(PROGRESS_PATH)
    posts = master_index["posts"]

    # Build collection lookup
    post_lookup = {p["shortcode"]: p for p in posts}

    # Find posts ready for analysis
    to_analyse = []
    for post in posts:
        sc = post["shortcode"]
        p = progress["posts"].get(sc, {})
        if p.get("transcribed") and not p.get("analysed"):
            post_dir = DOWNLOADS_DIR / sc
            if post_dir.exists():
                to_analyse.append(post)

    print(f"{len(to_analyse)} posts to analyse\n")

    analysed = 0
    failed = 0

    for i, post in enumerate(to_analyse, 1):
        sc = post["shortcode"]
        post_dir = DOWNLOADS_DIR / sc
        username = post.get("username", "")
        url = post.get("url", "")
        collections = post.get("collections", [])
        collection = collections[0] if collections else "_uncollected"

        # Read text data
        caption = read_text(post_dir / "caption.txt")
        transcript = read_text(post_dir / "transcript.txt")
        meta = load_json(post_dir / "meta.json") or {}

        # Run appropriate analyser
        try:
            if collection == "Travel":
                analysis = analyse_travel(caption, transcript, meta, username, url)
            elif collection == "Recipes":
                analysis = analyse_recipe(caption, transcript, meta, username, url)
            elif collection == "Stretching":
                analysis = analyse_stretching(caption, transcript, meta, username, url)
            elif collection == "Life Hacks etc":
                analysis = analyse_life_hack(caption, transcript, meta, username, url)
            else:
                analysis = analyse_uncollected(caption, transcript, meta, username, url)

            # Write analysis.json
            analysis_path = post_dir / "analysis.json"
            save_json(analysis_path, analysis)

            # Update progress
            progress["posts"].setdefault(sc, {})["analysed"] = True
            analysed += 1

            if i % 50 == 0 or i == len(to_analyse):
                save_json(PROGRESS_PATH, progress)

            # Brief log
            if collection == "Travel":
                detail = f"{analysis.get('country', '?')}/{analysis.get('city_or_region', '?')}"
            elif collection == "Recipes":
                detail = analysis.get("dish_name", "?")[:40]
            elif collection == "Stretching":
                detail = analysis.get("body_area", "?")
            elif collection == "Life Hacks etc":
                detail = analysis.get("category", "?")
            else:
                detail = analysis.get("best_guess_collection", "?")

            if i <= 20 or i % 50 == 0 or i == len(to_analyse):
                print(f"[{i}/{len(to_analyse)}] {sc} ({collection}) -> {detail}")

        except Exception as e:
            failed += 1
            print(f"[{i}/{len(to_analyse)}] {sc} FAILED: {e}")

    # Final save
    save_json(PROGRESS_PATH, progress)

    print(f"\n=== Analysis Complete ===")
    print(f"  Analysed: {analysed}")
    print(f"  Failed: {failed}")


if __name__ == "__main__":
    main()
