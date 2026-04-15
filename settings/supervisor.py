import os
from pathlib import Path

from deepagents import SubAgent
from dotenv import load_dotenv

load_dotenv()

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
DEFAULT_OPENAI_MODEL = "openai:gpt-5.4-mini"
SUPERVISOR_AGENT_NAME = "platform-supervisor"
APP_AI_MODE_ENV = "APP_AI_MODE"
APP_AI_MODE_MOCK = "mock"
APP_AI_MODE_LIVE = "live"
DEFAULT_APP_AI_MODE = APP_AI_MODE_MOCK
LLM_PROMPT_MODE_ENV = "LLM_PROMPT_MODE"
LLM_PROMPT_MODE_LIGHT = "light"
LLM_PROMPT_MODE_HEAVY = "heavy"
DEFAULT_LLM_PROMPT_MODE = LLM_PROMPT_MODE_HEAVY
LIGHT_PROMPT_LINE_COUNT = 3
SPECIALIST_MAX_OUTPUT_TOKENS_ENV = "SPECIALIST_MAX_OUTPUT_TOKENS"
SUPERVISOR_MAX_OUTPUT_TOKENS_ENV = "SUPERVISOR_MAX_OUTPUT_TOKENS"
SPECIALIST_TIMEOUT_SECONDS_ENV = "SPECIALIST_TIMEOUT_SECONDS"
DEFAULT_SPECIALIST_MAX_OUTPUT_TOKENS = 1200
DEFAULT_SUPERVISOR_MAX_OUTPUT_TOKENS = 1800
DEFAULT_SPECIALIST_TIMEOUT_SECONDS = 45


def load_prompt(prompt_name: str) -> str:
    prompt_text = (PROMPTS_DIR / prompt_name).read_text(encoding="utf-8").strip()
    if get_llm_prompt_mode() == LLM_PROMPT_MODE_LIGHT:
        return summarize_prompt(prompt_text)
    return prompt_text


def get_supervisor_system_prompt() -> str:
    return load_prompt("supervisor.md")


def get_specialist_subagents() -> list[SubAgent]:
    return [
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


def get_specialist_max_output_tokens() -> int:
    return get_int_env(
        SPECIALIST_MAX_OUTPUT_TOKENS_ENV,
        DEFAULT_SPECIALIST_MAX_OUTPUT_TOKENS,
    )


def get_supervisor_max_output_tokens() -> int:
    return get_int_env(
        SUPERVISOR_MAX_OUTPUT_TOKENS_ENV,
        DEFAULT_SUPERVISOR_MAX_OUTPUT_TOKENS,
    )


def get_specialist_timeout_seconds() -> int:
    return get_int_env(
        SPECIALIST_TIMEOUT_SECONDS_ENV,
        DEFAULT_SPECIALIST_TIMEOUT_SECONDS,
    )


def get_app_ai_mode() -> str:
    configured_mode = os.getenv(APP_AI_MODE_ENV, DEFAULT_APP_AI_MODE).strip().lower()
    if configured_mode in {APP_AI_MODE_MOCK, APP_AI_MODE_LIVE}:
        return configured_mode
    return DEFAULT_APP_AI_MODE


def get_llm_prompt_mode() -> str:
    configured_mode = os.getenv(
        LLM_PROMPT_MODE_ENV,
        DEFAULT_LLM_PROMPT_MODE,
    ).strip().lower()
    if configured_mode in {LLM_PROMPT_MODE_LIGHT, LLM_PROMPT_MODE_HEAVY}:
        return configured_mode
    return DEFAULT_LLM_PROMPT_MODE


def summarize_prompt(prompt_text: str) -> str:
    non_empty_lines = [line.strip() for line in prompt_text.splitlines() if line.strip()]
    summary_lines = non_empty_lines[:LIGHT_PROMPT_LINE_COUNT]
    if not summary_lines:
        return ""
    return "\n".join(summary_lines)


def has_openai_api_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def is_live_ai_enabled() -> bool:
    return get_app_ai_mode() == APP_AI_MODE_LIVE and has_openai_api_key()


def get_int_env(env_name: str, default: int) -> int:
    raw_value = os.getenv(env_name, "").strip()
    if not raw_value:
        return default
    try:
        parsed_value = int(raw_value)
    except ValueError:
        return default
    return parsed_value if parsed_value > 0 else default
