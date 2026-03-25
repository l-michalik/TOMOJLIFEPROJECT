from deepagents import create_deep_agent
from dotenv import load_dotenv
import os
from typing import Literal
from tavily import TavilyClient

load_dotenv()

tavily_client = TavilyClient()

def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """
    Run a web search using TavilyClient.

    Args:
        query (str): The search query.
        max_results (int): Maximum number of results to return. Default is 5.
        topic (Literal): The topic of the search. Default is "general".
        include_raw_content (bool): Whether to include raw content in results. Default is False.

    Returns:
        dict: Search results.
    """
    return tavily_client.search(
        query=query,
        max_results=max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )

RESEARCH_INSTRUCTIONS = """You are an expert researcher. Your job is to conduct thorough research and then write a polished report.

You have access to an internet search tool as your primary means of gathering information.

## `internet_search`

Use this to run an internet search for a given query. You can specify the max number of results to return, the topic, and whether raw content should be included.
"""

agent = create_deep_agent(
    tools=[internet_search],
    system_prompt=RESEARCH_INSTRUCTIONS,
    model="openai:gpt-5.4",
)

def main():
    user_query = "What is langgraph?"
    result = agent.invoke({"messages": [{"role": "user", "content": user_query}]})
    
    print(result["messages"][-1].content)

if __name__ == "__main__":
    main()