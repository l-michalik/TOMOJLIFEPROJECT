from deepagents import create_deep_agent
from dotenv import load_dotenv

load_dotenv()

def get_weather(city: str) -> str:
    """A mock function to get the weather for a city. In a real implementation, this would call an API."""
    return f"It's always sunny in {city}!"

agent = create_deep_agent(
    tools=[get_weather],
    system_prompt="You are a helpful assistant",
    model="gpt-4.1-mini"
)

response = agent.invoke(
    {"messages": [{"role": "user", "content": "what is the weather in sf"}]}
)

print(response["messages"][-1].content)