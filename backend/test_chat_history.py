"""
Test: multi-turn conversation with real chat_history.
Expect: the second response should reference/respect context from the first turn
(e.g. narrowing by color after an initial broad search).
"""
from langchain_core.messages import HumanMessage, AIMessage
from agents.stylist_agent import run_stylist_agent

chat_history = []

# --- Turn 1 ---
turn1_input = "I'm looking for a bridal lehenga for my wedding"
print(f"\n{'='*60}\nTURN 1: {turn1_input}\n{'='*60}")
turn1_result = run_stylist_agent(turn1_input, chat_history)
print("RESULT:", turn1_result)

# Manually append to history the way your chat route should be doing it
chat_history.append(HumanMessage(content=turn1_input))
chat_history.append(AIMessage(content=turn1_result))

# --- Turn 2: follow-up that only makes sense with context ---
turn2_input = "Do you have anything in that style but in a lighter color?"
print(f"\n{'='*60}\nTURN 2: {turn2_input}\n{'='*60}")
turn2_result = run_stylist_agent(turn2_input, chat_history)
print("RESULT:", turn2_result)

# Sanity check
if "iteration limit" in turn2_result.lower() or "time limit" in turn2_result.lower():
    print("❌ FAIL: turn 2 hit execution limit")
else:
    print("✅ Turn 2 completed — manually verify it references turn 1 context")