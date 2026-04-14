import os
from pathlib import Path

from deepagents import SubAgent, create_deep_agent

from contracts.task_request import InputStatus, TaskRequest
from contracts.task_response import TaskResponse

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
DEFAULT_OPENAI_MODEL = "openai:gpt-5.4-mini"


def load_prompt(prompt_name: str) -> str:
    return (PROMPTS_DIR / prompt_name).read_text(encoding="utf-8").strip()


SUPERVISOR_SYSTEM_PROMPT = load_prompt("supervisor.md")
SPECIALIST_SUBAGENTS: list[SubAgent] = [
    {
        "name": "deployment-agent",
        "description": "Plans application and service deployment steps.",
        "system_prompt": load_prompt("deployment_agent.md"),
    },
    {
        "name": "infra-agent",
        "description": "Plans infrastructure and configuration changes.",
        "system_prompt": load_prompt("infra_agent.md"),
    },
    {
        "name": "ci-cd-agent",
        "description": "Plans pipeline, build, test, and release flow steps.",
        "system_prompt": load_prompt("ci_cd_agent.md"),
    },
]


def get_openai_model(explicit_model: str | None = None) -> str:
    if explicit_model:
        return explicit_model
    return os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)


def create_supervisor_agent(model: str | None = None):
    return create_deep_agent(
        model=get_openai_model(explicit_model=model),
        system_prompt=SUPERVISOR_SYSTEM_PROMPT,
        subagents=SPECIALIST_SUBAGENTS,
        name="platform-supervisor",
    )


def read_last_message_text(result: dict) -> str:
    messages = result.get("messages", [])
    if not messages:
        return ""
    last_message = messages[-1]
    content = getattr(last_message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
        return "\n".join(part for part in text_parts if part)
    return str(content)


def run_supervisor_agent(
    task_request: TaskRequest, model: str | None = None
) -> TaskResponse:
    if task_request.input_status == InputStatus.NEEDS_CLARIFICATION:
        return TaskResponse.from_clarification_request(task_request=task_request)

    selected_model = get_openai_model(explicit_model=model)
    agent = create_supervisor_agent(model=selected_model)
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": task_request.to_prompt(),
                }
            ]
        }
    )
    return TaskResponse.from_planned_task(
        task_request=task_request,
        model=selected_model,
        answer=read_last_message_text(result=result),
    )
