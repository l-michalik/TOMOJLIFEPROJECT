import os
from pathlib import Path

from deepagents import SubAgent

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
DEFAULT_OPENAI_MODEL = "openai:gpt-5.4-mini"
SUPERVISOR_AGENT_NAME = "platform-supervisor"


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
