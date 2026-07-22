from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from tools.product_search_tool import search_products
from config import settings
import logging
import traceback

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are VORA, an expert bridal fashion consultant for VORAZ (luxury Indian bridal couture).
Help customers find their perfect lehenga by understanding their style, occasion, and color preferences.
Always use the search_products tool to find relevant products before responding.
Call search_products only once per customer request unless the first search returns
no results at all — do not repeatedly rephrase the same query.
Provide warm, personalized recommendations with specific product details."""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("placeholder", "{chat_history}"),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

def run_stylist_agent(user_message: str, chat_history: list) -> str:
    try:
        logger.debug(f"=== AGENT START | input: {user_message} ===")

        llm = ChatOpenAI(
            model=settings.openrouter_model_id,
            temperature=0.3,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base=settings.openrouter_base_url,
        )

        tools = [search_products]

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

        response = agent_executor.invoke({
            "input": user_message,
            "chat_history": chat_history,
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