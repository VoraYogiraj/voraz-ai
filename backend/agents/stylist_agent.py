from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from tools.product_search_tool import search_products, search_products_filtered
from agents.memory_store import get_or_create_profile
from config import settings
import logging
import traceback

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Maps the frontend/profile's internal avatar_type values to the exact
# order_type strings stored in Supabase (must match Shopify metafield values
# exactly — see product metafield definitions in Shopify admin).
AVATAR_TO_ORDER_TYPE = {
    "ready_to_wear": "Ready to Ship",
    "custom": "Choose & Customize",
    "bespoke": "Fully Bespoke",
}

SYSTEM_PROMPT = """You are VORA, an expert bridal fashion consultant for VORAZ (luxury Indian bridal couture).
Help customers find their perfect lehenga by understanding their style, occasion, and color preferences.

You have two search tools:
- search_products_filtered: use this FIRST whenever the customer's known profile
  (shown below, if available) already has occasion, style, budget, or location
  slots filled in. It filters directly against the catalog and is more precise.
- search_products: use this if search_products_filtered returns no results, or
  if the customer's profile has no relevant slots filled in yet — it searches
  by semantic similarity to the customer's description instead.

Call a search tool only once per customer request unless the first search returns
no results at all — do not repeatedly rephrase the same query.

Known customer profile so far:
{profile_context}

{order_type_constraint}

Provide warm, personalized recommendations with specific product details."""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("placeholder", "{chat_history}"),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])


def _build_order_type_constraint(session_id: str) -> str:
    """Resolves the customer's chosen path to the exact order_type string
    used in the product catalog, and returns a hard instruction for the
    agent — so path filtering doesn't depend on the LLM correctly
    translating avatar_type on its own."""
    if not session_id:
        return ""

    try:
        profile = get_or_create_profile(session_id)
        avatar_type = profile.get("avatar_type") if profile else None
        order_type = AVATAR_TO_ORDER_TYPE.get(avatar_type)

        if order_type:
            return (
                f"IMPORTANT: This customer is on the '{order_type}' path. "
                f"You MUST pass order_type=\"{order_type}\" on every call to "
                f"search_products or search_products_filtered. Never show "
                f"products from a different order_type."
            )
        return ""
    except Exception as e:
        logger.warning(f"Could not resolve order_type constraint for session {session_id}: {e}")
        return ""


def _build_profile_context(session_id: str) -> str:
    """Pulls the customer's known profile slots and formats them as
    plain text for the system prompt, so the agent's tool calls are
    grounded in what the Profiler already extracted instead of
    re-guessing from raw conversation text."""
    if not session_id:
        return "No profile available yet."

    try:
        profile = get_or_create_profile(session_id)
        if not profile:
            return "No profile available yet."

        parts = []
        if profile.get("avatar_type"):
            parts.append(f"Order type: {profile['avatar_type']}")
        if profile.get("event_type"):
            parts.append(f"Occasion: {profile['event_type']}")
        if profile.get("style_prefs"):
            parts.append(f"Style preferences: {profile['style_prefs']}")
        if profile.get("budget_min") or profile.get("budget_max"):
            parts.append(f"Budget: ₹{profile.get('budget_min', 0):,.0f}–₹{profile.get('budget_max', 0):,.0f}")
        if profile.get("location"):
            parts.append(f"Location: {profile['location']}")

        return "\n".join(parts) if parts else "No profile slots filled in yet."
    except Exception as e:
        logger.warning(f"Could not load profile for session {session_id}: {e}")
        return "No profile available yet."


def run_stylist_agent(user_message: str, chat_history: list, session_id: str = None) -> str:
    try:
        logger.debug(f"=== AGENT START | input: {user_message} | session_id: {session_id} ===")

        llm = ChatOpenAI(
            model=settings.openrouter_model_id,
            temperature=0.3,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base=settings.openrouter_base_url,
        )

        tools = [search_products_filtered, search_products]

        agent = create_tool_calling_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            max_iterations=10,
            max_execution_time=30,          # seconds — hard safety net
            early_stopping_method="generate",  # produce best-effort answer instead of the raw limit message
            handle_parsing_errors=True,
            return_intermediate_steps=True,
        )

        profile_context = _build_profile_context(session_id)
        order_type_constraint = _build_order_type_constraint(session_id)

        response = agent_executor.invoke({
            "input": user_message,
            "chat_history": chat_history,
            "profile_context": profile_context,
            "order_type_constraint": order_type_constraint,
        })

        logger.debug(f"=== INTERMEDIATE STEPS: {response.get('intermediate_steps')} ===")
        logger.debug(f"=== AGENT OUTPUT: {response.get('output')} ===")

        output = response.get("output")
        if not output or "iteration limit" in output.lower() or "time limit" in output.lower():
            logger.warning("Agent hit execution limit despite early_stopping_method")
            return "I found a few options for you, but had trouble finalizing the recommendation. Could you tell me a bit more about the style or occasion you're looking for?"

        return output

    except Exception as e:
        print("=== STYLIST AGENT ERROR ===")
        print(traceback.format_exc())
        logger.error(f"Stylist agent error: {e}", exc_info=True)
        return "Our stylist is temporarily unavailable. Please try again."