from __future__ import annotations

from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SUPERVISOR_SYSTEM_PROMPT_PATH = PROMPTS_DIR / "supervisor_system_prompt.md"


def build_supervisor_system_prompt() -> str:
    return SUPERVISOR_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()


SUPERVISOR_SYSTEM_PROMPT = build_supervisor_system_prompt()
