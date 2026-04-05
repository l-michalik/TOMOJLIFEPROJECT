from dotenv import load_dotenv
import os
from typing import Literal
from tavily import TavilyClient
from deepagents import create_deep_agent
from langchain.agents.middleware import wrap_tool_call

load_dotenv()

tavily_client = TavilyClient()

def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """Run a web search"""
    print(f"Running internet search for query: {query}")
    return tavily_client.search(
        query,
        max_results=max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )
    
# System prompt to steer the agent to be an expert researcher
research_instructions = """You are an expert researcher. Your job is to conduct thorough research and then write a polished report.

You have access to an internet search tool as your primary means of gathering information.

## `internet_search`

Use this to run an internet search for a given query. You can specify the max number of results to return, the topic, and whether raw content should be included.
"""

call_count = [0]  # Use list to allow modification in nested function

@wrap_tool_call
def log_tool_calls(request, handler):
    """Intercept and log every tool call - demonstrates cross-cutting concern."""
    call_count[0] += 1
    tool_name = request.name if hasattr(request, 'name') else str(request)

    print(f"[Middleware] Tool call #{call_count[0]}: {tool_name}")
    print(f"[Middleware] Arguments: {request.args if hasattr(request, 'args') else 'N/A'}")

    # Execute the tool call
    result = handler(request)

    # Log the result
    print(f"[Middleware] Tool call #{call_count[0]} completed")

    return result

agent = create_deep_agent(
    model="openai:gpt-4.1",
    tools=[internet_search],
    system_prompt=research_instructions,
    middleware=[log_tool_calls],
)

result = agent.invoke({"messages": [{"role": "user", "content": "What is langgraph? Check the web and write a report."}]})

# Print the agent's response
print(result["messages"][-1].content)