import os
from pathlib import Path

from deepagents import SubAgent

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
DEFAULT_OPENAI_MODEL = "openai:gpt-5.4-mini"
SUPERVISOR_AGENT_NAME = "platform-supervisor"
APP_AI_MODE_ENV = "APP_AI_MODE"
APP_AI_MODE_MOCK = "mock"
APP_AI_MODE_LIVE = "live"
DEFAULT_APP_AI_MODE = APP_AI_MODE_MOCK


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


def get_app_ai_mode() -> str:
    configured_mode = os.getenv(APP_AI_MODE_ENV, DEFAULT_APP_AI_MODE).strip().lower()
    if configured_mode in {APP_AI_MODE_MOCK, APP_AI_MODE_LIVE}:
        return configured_mode
    return DEFAULT_APP_AI_MODE


def has_openai_api_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def is_live_ai_enabled() -> bool:
    return get_app_ai_mode() == APP_AI_MODE_LIVE and has_openai_api_key()
