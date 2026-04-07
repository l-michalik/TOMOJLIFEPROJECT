from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model
from tools import tavily_search, think_tool
from dotenv import load_dotenv
from prompts import RESEARCHER_INSTRUCTIONS, SUBAGENT_DELEGATION_INSTRUCTIONS, RESEARCH_WORKFLOW_INSTRUCTIONS
from datetime import datetime

load_dotenv()

model = init_chat_model(model="anthropic:claude-sonnet-4-5-20250929", temperature=0.0)

INSTRUCTIONS = (
    RESEARCH_WORKFLOW_INSTRUCTIONS
    + "\n\n"
    + "=" * 80
    + "\n\n"
    + SUBAGENT_DELEGATION_INSTRUCTIONS.format(
        max_concurrent_research_units=3,
        max_researcher_iterations=3,
    )
)

research_sub_agent = {
    "name": "research-agent",
    "description": "Delegate research to the sub-agent researcher. Only give this researcher one topic at a time.",
    "system_prompt": RESEARCHER_INSTRUCTIONS.format(date=datetime.now().strftime("%Y-%m-%d")),
    "tools": [tavily_search, think_tool],
}

agent = create_deep_agent(
    model=model,
    tools=[tavily_search, think_tool],
    system_prompt=INSTRUCTIONS,
    subagents=[research_sub_agent],
)
