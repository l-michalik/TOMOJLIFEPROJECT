from __future__ import annotations

from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_markdown_prompt(prompt_name: str) -> str:
    prompt_path = _resolve_prompt_path(prompt_name)
    return prompt_path.read_text(encoding="utf-8").strip()


def _resolve_prompt_path(prompt_name: str) -> Path:
    prompt_file_name = prompt_name if prompt_name.endswith(".md") else f"{prompt_name}.md"
    prompt_path = (PROMPTS_DIR / prompt_file_name).resolve()

    if PROMPTS_DIR.resolve() not in prompt_path.parents:
        raise ValueError(f"Prompt must be inside {PROMPTS_DIR}")

    return prompt_path
