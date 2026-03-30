import modal
import csv
import io
import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

from langchain_modal import ModalSandbox

app = modal.App.lookup("data-analysis", create_if_missing=True)
image = modal.Image.debian_slim().pip_install("pandas", "matplotlib")
sb = modal.Sandbox.create(app=app, image=image)
backend = ModalSandbox(sandbox=sb)

REMOTE_DATA_DIR = "/home/daytona/data"
REMOTE_CSV_PATH = f"{REMOTE_DATA_DIR}/sales_data.csv"

# Sample data
data = [
    ["Date", "Product", "Units Sold", "Revenue"],
    ["2025-08-01", "Widget A", 10, 250],
    ["2025-08-02", "Widget B", 5, 125],
    ["2025-08-03", "Widget A", 7, 175],
    ["2025-08-04", "Widget C", 3, 90],
    ["2025-08-05", "Widget B", 8, 200],
]

# Create CSV bytes
buf = io.StringIO()
csv.writer(buf).writerows(data)
csv_bytes = buf.getvalue().encode("utf-8")

# Ensure the sandbox directory exists, then upload the CSV to the same path
# the agent will be asked to analyze.
sb.exec("mkdir", "-p", REMOTE_DATA_DIR)
sb.filesystem.write_bytes(csv_bytes, REMOTE_CSV_PATH)

from langchain.tools import tool

@tool(parse_docstring=True)
def save_analysis_locally(text: str, file_path: str | None = None) -> str:
    """Save analysis and optional file locally.

    Args:
        text: (str) text content of the message
        file_path: (str) file path of attachment in the filesystem.
    """
    output_dir = "./analysis_output"
    os.makedirs(output_dir, exist_ok=True)

    # Save the message
    message_file = os.path.join(output_dir, "analysis_message.txt")
    with open(message_file, "w") as f:
        f.write(text)

    # Save the file if provided
    if file_path:
        local_file_path = os.path.join(output_dir, os.path.basename(file_path))
        fp = backend.download_files([file_path])
        with open(local_file_path, "wb") as f:
            f.write(fp[0].content)

    return f"Analysis saved locally in {output_dir}."

import uuid

from langgraph.checkpoint.memory import InMemorySaver
from deepagents import create_deep_agent

checkpointer = InMemorySaver()

agent = create_deep_agent(
    model="openai:gpt-4.1",
    tools=[save_analysis_locally],
    backend=backend,
    checkpointer=checkpointer,
)

thread_id = str(uuid.uuid4())
config = {"configurable": {"thread_id": thread_id}}

input_message = {
    "role": "user",
    "content": (
        f"Analyze {REMOTE_CSV_PATH} and generate a beautiful plot. "
        "When finished, save your analysis and the plot locally using the tool."
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
