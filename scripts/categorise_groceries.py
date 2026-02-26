"""Auto-categorise grocery items into supermarket categories.

Simple keyword-based categoriser used during sheet import to replace
the flat "Shopping List" fallback with meaningful categories for PDF layout.

Usage (as module):
    from scripts.categorise_groceries import categorise_item
    category = categorise_item("Greek yoghurt")  # -> "Dairy & Eggs"
"""

# Keywords mapped to supermarket categories.
# Order matters: first match wins. More specific categories (Frozen,
# Household, Drinks) are checked before broad ones (Fruit & Veg).
CATEGORY_RULES: dict[str, list[str]] = {
    "Household": [
        "loo roll", "toilet roll", "kitchen roll", "bin bag",
        "cling film", "tin foil", "aluminium foil", "washing up",
        "dishwasher", "detergent", "soap", "shampoo",
    ],
    "Frozen": [
        "frozen", "ice cream", "ice loll",
    ],
    "Drinks": [
        "juice", "squash", "chocolate milk", "lemonade", "cola",
        "coffee", "tea bag", "fizzy",
    ],
    "Breakfast": [
        "cereal", "granola", "porridge", "oat", "weetabix",
    ],
    "Dairy & Eggs": [
        "milk", "yoghurt", "yogurt", "cheese", "cream cheese",
        "soft cheese", "cheddar", "mozzarella", "parmesan", "feta",
        "halloumi", "mascarpone", "ricotta", "brie", "camembert",
        "cream", "double cream", "single cream", "sour cream",
        "creme fraiche", "butter", "margarine", "egg",
    ],
    "Meat & Fish": [
        "chicken", "beef", "pork", "lamb", "mince", "steak", "gammon",
        "bacon", "ham", "sausage", "brisket", "ribs", "turkey",
        "duck", "salmon", "cod", "haddock", "tuna", "prawn", "shrimp",
        "fish finger", "fish cake", "fish fillet", "sea bass", "mackerel",
        "chorizo", "pepperoni", "salami",
    ],
    "Bakery": [
        "bread", "wraps", "tortilla", "pitta", "naan", "bagel",
        "baguette", "ciabatta", "focaccia", "crumpet",
        "muffin", "croissant", "pizza base", "pizza dough",
        "brioche", "sourdough", "flatbread", "bread roll",
    ],
    "Tinned & Dry": [
        "tin of", "tinned", "canned", "chopped tom", "baked bean",
        "chickpea", "lentil", "kidney bean", "black bean", "butter bean",
        "coconut milk", "passata", "tomato puree", "tomato paste",
        "rice", "pasta", "noodle", "couscous", "spaghetti", "penne",
        "fusilli", "lasagne sheet", "flour", "sugar", "stock cube",
        "stock pot", "oxo", "gravy", "stuffing",
    ],
    "Condiments & Sauces": [
        "ketchup", "mayo", "mayonnaise", "mustard", "soy sauce",
        "worcester", "hot sauce", "sriracha", "pesto", "chutney",
        "pickle", "vinegar", "olive oil", "oil", "honey",
        "jam", "marmalade", "peanut butter", "nutella", "marmite",
        "salad dressing", "bbq sauce",
    ],
    "Snacks & Desserts": [
        "crisp", "chocolate", "biscuit", "cake", "puds", "pudding",
        "dessert", "jelly", "custard", "popcorn",
    ],
    "Fruit & Veg": [
        "apple", "banana", "orange", "lemon", "lime", "pear", "grape",
        "strawberr", "blueberr", "raspberr", "mango", "melon", "pineapple",
        "avocado", "tomato", "toms", "cherry tom", "cucumber", "pepper",
        "onion", "garlic", "ginger", "potato", "sweet potato", "carrot",
        "broccoli", "cauliflower", "courgette", "aubergine", "mushroom",
        "spinach", "lettuce", "rocket", "kale", "cabbage", "spring onion",
        "leek", "celery", "sweetcorn", "corn on", "peas", "green bean",
        "runner bean", "asparagus", "beetroot", "radish", "parsnip",
        "turnip", "swede", "butternut", "squash", "chilli", "jalapen",
        "coriander", "basil", "mint", "parsley", "thyme", "rosemary",
        "salad", "watercress", "pak choi", "beansprout", "edamame",
        "spring greens", "tenderstem", "baby corn",
    ],
}


def categorise_item(item: str) -> str:
    """Return the best supermarket category for a grocery item.

    Performs case-insensitive substring matching against CATEGORY_RULES.
    Returns "Other" if no keyword matches.
    """
    lower = item.lower().strip()
    for category, keywords in CATEGORY_RULES.items():
        for keyword in keywords:
            if keyword in lower:
                return category
    return "Other"


# ---- CLI helper ----
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            print(f"{arg!r} -> {categorise_item(arg)}")
    else:
        # Quick self-test
        tests = [
            ("Greek yoghurt", "Dairy & Eggs"),
            ("Chicken breast", "Meat & Fish"),
            ("Cucumber", "Fruit & Veg"),
            ("Wraps", "Bakery"),
            ("Frozen peas", "Frozen"),
            ("Loo roll", "Household"),
            ("Granola", "Breakfast"),
            ("Orange juice", "Drinks"),
            ("Puds", "Snacks & Desserts"),
            ("Mystery item", "Other"),
        ]
        for item, expected in tests:
            result = categorise_item(item)
            status = "OK" if result == expected else f"FAIL (got {result})"
            print(f"  {item:25s} -> {result:25s} [{status}]")
