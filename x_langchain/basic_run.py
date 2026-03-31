from dotenv import load_dotenv
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

load_dotenv()

def get_weather(city: str) -> str:
    """Get weather for a given city."""
    return f"It's always sunny in {city}!"

agent = create_deep_agent(
    tools=[get_weather],
    model=ChatOpenAI(model="gpt-4.1", temperature=0),
    system_prompt="You are a helpful assistant",
)

# Run the agent
agent.invoke(
    {"messages": [{"role": "user", "content": "what is the weather in sf"}]}
)