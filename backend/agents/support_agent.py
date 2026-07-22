from langchain_openai import ChatOpenAI
from langchain.agents import create_react_agent, AgentExecutor
from langchain import hub
from config import settings
import logging

logger = logging.getLogger(__name__)

prompt = hub.pull("hwchase17/react")

SYSTEM_PROMPT = """You are the VORA Support Specialist. You help customers track orders.
Ask for an Order Number (#XXXX) or Email. 
Call the tools immediately once you have that info.
Be concise and helpful."""

def run_support_agent(user_message: str, chat_history: list) -> str:
    """
    Run support agent for order tracking.
    chat_history: list of {"role": "user"/"assistant", "content": "..."} dicts
    """
    try:
        llm = ChatOpenAI(
            model=settings.openrouter_model_id,
            temperature=0.2,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base=settings.openrouter_base_url
        )
        
        # TODO: Import real tools once shopify_order_tool.py is ready
        # tools = [get_order_status, get_orders_by_customer_email]
        tools = []  # Placeholder until tools are implemented
        
        agent = create_react_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=False,
            max_iterations=5,
            handle_parsing_errors=True
        )
        
        # Format history for context
        history_text = "\n".join([
            f"{h['role'].upper()}: {h['content']}"
            for h in chat_history[-4:]  # Last 4 turns only
        ])
        
        input_text = f"{SYSTEM_PROMPT}\n\nContext:\n{history_text}\n\nUser: {user_message}"
        response = agent_executor.invoke({"input": input_text})
        return response.get("output", "Unable to process request.")
    
    except Exception as e:
        logger.error(f"Support agent error: {e}")
        return "Support team unavailable. Please email support@voraz.com"

def should_use_support_agent(message: str) -> bool:
    """Route to support agent if order/tracking keywords detected."""
    keywords = ["order", "track", "delivery", "status", "ship", "where is my", "when will"]
    return any(word in message.lower() for word in keywords)