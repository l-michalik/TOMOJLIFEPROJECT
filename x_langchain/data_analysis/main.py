import modal
import csv
import io
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()  # Load environment variables from .env file

from langchain_modal import ModalSandbox

app = modal.App.lookup("data-analysis-app", create_if_missing=True)
image = modal.Image.debian_slim().pip_install("pandas", "matplotlib", "seaborn")

# Create the sandbox
modal_sandbox = modal.Sandbox.create(app=app, image=image)
backend = ModalSandbox(sandbox=modal_sandbox)

# Create sample sales data
data = [
    ["Date", "Product", "Units Sold", "Revenue"],
    ["2025-08-01", "Widget A", 10, 250],
    ["2025-08-02", "Widget B", 5, 125],
    ["2025-08-03", "Widget A", 7, 175],
    ["2025-08-04", "Widget C", 3, 90],
    ["2025-08-05", "Widget B", 8, 200],
]

# Write data to CSV file
Path("data").mkdir(exist_ok=True)
with open("data/sales_data.csv", "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerows(data)
modal_sandbox.filesystem.write_bytes(
    Path("data/sales_data.csv").read_bytes(), "/tmp/sales_data.csv"
)
    
from langchain.tools import tool
from slack_sdk import WebClient


slack_token = os.environ["SLACK_USER_TOKEN"]
slack_client = WebClient(token=slack_token)


@tool(parse_docstring=True)
def slack_send_message(text: str, file_path: str | None = None) -> str:
    """Send message, optionally including attachments such as images.

    Args:
        text: (str) text content of the message
        file_path: (str) file path of attachment in the filesystem.
    """
    if not file_path:
        slack_client.chat_postMessage(channel=channel, text=text)
    else:
        slack_client.files_upload_v2(
            channel="C0AQJCNS45N",
            content=modal_sandbox.filesystem.read_bytes(file_path),
            initial_comment=text,
        )

    return "Message sent."

import uuid

from langgraph.checkpoint.memory import InMemorySaver
from deepagents import create_deep_agent


checkpointer = InMemorySaver()

agent = create_deep_agent(
    model="openai:gpt-4.1",
    tools=[slack_send_message],
    backend=backend,
    checkpointer=checkpointer,
)

thread_id = str(uuid.uuid4())
config={"configurable": {"thread_id": thread_id}}

input_message = {
    "role": "user",
    "content": (
        "Analyze /tmp/sales_data.csv and generate a beautiful plot. "
        "When finished, send your analysis and the plot to Slack using the tool."
    ),
}
for step in agent.stream(
    {"messages": [input_message]},
    config,
    stream_mode="updates",
):
    for _, update in step.items():
        if update and (messages := update.get("messages")) and isinstance(messages, list):
            for message in messages:
                message.pretty_print()
