"""
Test: occasion synonym mapping across the full catalog vocabulary.
Expect: each of these should return real products with occasion tags
matching what was asked (or a graceful no-match, never an error).
"""
from tools.product_search_tool import search_products, expand_occasion

# --- Unit-level check on the mapping function itself ---
print("=== expand_occasion() unit checks ===")
test_terms = {
    "wedding": "bridal",
    "shaadi": "bridal",
    "sangeet": "sangeet",
    "mehndi": "sangeet",
    "engagement": "engagement",
    "roka": "engagement",
    "reception": "reception",
    "cocktail party": "cocktail party",  # unmapped, should pass through unchanged
    None: None,
}
for term, expected in test_terms.items():
    actual = expand_occasion(term)
    status = "✅" if actual == expected else "❌"
    print(f"{status} expand_occasion({term!r}) = {actual!r} (expected {expected!r})")

# --- End-to-end tool checks ---
print("\n=== search_products() end-to-end checks ===")
TEST_CASES = [
    {"query": "elegant lehenga", "occasion": "sangeet"},
    {"query": "lehenga", "occasion": "engagement"},
    {"query": "lehenga", "occasion": "reception"},
    {"query": "lehenga", "occasion": "shaadi"},   # synonym for bridal
    {"query": "lehenga", "occasion": "mehndi"},   # synonym for sangeet
]

for case in TEST_CASES:
    print(f"\n--- occasion={case['occasion']!r} ---")
    result = search_products.invoke(case)
    if "No products found" in result:
        print("⚠️  No results — check if this occasion has catalog coverage")
    elif "Error" in result:
        print("❌ FAIL:", result)
    else:
        # print just the product titles for a quick scan
        titles = [line for line in result.split("\n") if line.startswith("PRODUCT:")]
        print(f"✅ {len(titles)} product(s) returned:")
        for t in titles:
            print("   ", t)