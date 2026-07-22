"""
Test: query with no reasonable product match.
Expect: graceful "no products found" style message, NOT a hallucinated
product, NOT an iteration-limit error.
"""
from agents.stylist_agent import run_stylist_agent

TEST_QUERIES = [
    "do you sell men's formal suits",
    "I need a scuba diving wetsuit for my wedding",
    "show me lehengas under ₹500",  # unrealistically low budget, should find nothing in range
]

for q in TEST_QUERIES:
    print(f"\n{'='*60}\nQUERY: {q}\n{'='*60}")
    result = run_stylist_agent(q, [])
    print("RESULT:", result)

    # Basic sanity checks
    lowered = result.lower()
    if "iteration limit" in lowered or "time limit" in lowered:
        print("❌ FAIL: hit execution limit")
    elif "http" in lowered and "myshopify.com" in lowered:
        print("⚠️  WARNING: returned a product link — verify it's actually relevant, not hallucinated")
    else:
        print("✅ Looks like a graceful no-match response")