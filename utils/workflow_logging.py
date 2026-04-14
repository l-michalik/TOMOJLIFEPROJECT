import logging
import os
import json
import sys

try:
    from rich.console import Console
    from rich.panel import Panel
except ImportError:  # pragma: no cover
    Console = None
    Panel = None


PROMPT_LOG_MODE_ENV = "AI_REQUEST_LOG_PROMPT_MODE"
RESPONSE_LOG_MODE_ENV = "AI_RESPONSE_LOG_MODE"
PROMPT_LOG_MODE_GENERIC = "generic"
PROMPT_LOG_MODE_FULL = "full"
PROMPT_LOG_MODE_OFF = "off"
DEFAULT_PROMPT_LOG_MODE = PROMPT_LOG_MODE_GENERIC
DEFAULT_RESPONSE_LOG_MODE = PROMPT_LOG_MODE_GENERIC
_rich_console = Console(file=sys.stdout, soft_wrap=True) if Console else None


def configure_application_logging() -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)


def get_application_logger(name: str) -> logging.Logger:
    configure_application_logging()
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def get_prompt_log_mode() -> str:
    configured_mode = os.getenv(PROMPT_LOG_MODE_ENV, DEFAULT_PROMPT_LOG_MODE).strip().lower()
    if configured_mode in {
        PROMPT_LOG_MODE_GENERIC,
        PROMPT_LOG_MODE_FULL,
        PROMPT_LOG_MODE_OFF,
    }:
        return configured_mode
    return DEFAULT_PROMPT_LOG_MODE


def get_response_log_mode() -> str:
    configured_mode = os.getenv(RESPONSE_LOG_MODE_ENV, DEFAULT_RESPONSE_LOG_MODE).strip().lower()
    if configured_mode in {
        PROMPT_LOG_MODE_GENERIC,
        PROMPT_LOG_MODE_FULL,
        PROMPT_LOG_MODE_OFF,
    }:
        return configured_mode
    return DEFAULT_PROMPT_LOG_MODE


def build_prompt_log_content(
    *,
    prompt: str,
    generic_prompt: str | None = None,
    mode: str | None = None,
) -> str | None:
    selected_mode = mode or get_prompt_log_mode()
    if selected_mode == PROMPT_LOG_MODE_OFF:
        return None
    if selected_mode == PROMPT_LOG_MODE_FULL:
        return prompt
    if generic_prompt:
        return generic_prompt
    return prompt.splitlines()[0].strip() if prompt.strip() else None


def build_response_log_content(
    *,
    response_text: str,
    generic_response: str | None = None,
    mode: str | None = None,
) -> str | None:
    selected_mode = mode or get_response_log_mode()
    if selected_mode == PROMPT_LOG_MODE_OFF:
        return None
    if selected_mode == PROMPT_LOG_MODE_FULL:
        return response_text
    if generic_response:
        return generic_response
    return response_text.splitlines()[0].strip() if response_text.strip() else None


def render_prompt_log_box(
    *,
    title: str,
    body: str,
) -> None:
    if _rich_console and Panel:
        _rich_console.print(
            Panel.fit(
                body,
                title=title,
                border_style="bright_cyan",
                padding=(0, 1),
            )
        )
        return

    border = "=" * max(len(title), len(body), 24)
    print(border, file=sys.stdout)
    print(title, file=sys.stdout)
    print(border, file=sys.stdout)
    print(body, file=sys.stdout)
    print(border, file=sys.stdout)


def build_prompt_log_box_body(
    *,
    agent_name: str | None,
    prompt_log_content: str,
    step_id: str | None = None,
    owner_agent: str | None = None,
    task_description: str | None = None,
    status: str | None = None,
) -> str:
    if step_id and owner_agent and task_description and status:
        lines = [
            f"step_id: {step_id}",
            f"owner_agent: {owner_agent}",
            f"task_description: {task_description}",
            f"status: {status}",
        ]
        return "\n".join(lines)

    resolved_agent_name = agent_name or "Supervisor"
    lines = [f"Agent: {resolved_agent_name}"]
    if step_id:
        lines.append(f"Step: {step_id}")
    lines.append(f"Action: {prompt_log_content}")
    return "\n".join(lines)


def build_response_log_box_body(
    *,
    agent_name: str | None,
    response_log_content: str,
    step_id: str | None = None,
    status: str | None = None,
    summary: str | None = None,
    owner_agent: str | None = None,
) -> str:
    if step_id and status and summary is not None and owner_agent:
        lines = [
            f"step_id: {step_id}",
            f"status: {status}",
            f"summary: {summary}",
            f"owner_agent: {owner_agent}",
        ]
        return "\n".join(lines)

    resolved_agent_name = agent_name or "Supervisor"
    lines = [f"Agent: {resolved_agent_name}"]
    if step_id:
        lines.append(f"Step: {step_id}")
    lines.append(f"Result: {response_log_content}")
    return "\n".join(lines)


def log_ai_request(
    logger: logging.Logger,
    *,
    request_id: str,
    model: str,
    prompt: str,
    agent_name: str | None = None,
    step_id: str | None = None,
    generic_prompt: str | None = None,
    owner_agent: str | None = None,
    task_description: str | None = None,
    status: str | None = None,
) -> None:
    prompt_log_content = build_prompt_log_content(
        prompt=prompt,
        generic_prompt=generic_prompt,
    )
    if prompt_log_content:
        render_prompt_log_box(
            title="AI Prompt Preview",
            body=build_prompt_log_box_body(
                agent_name=agent_name,
                step_id=step_id,
                prompt_log_content=prompt_log_content,
                owner_agent=owner_agent,
                task_description=task_description,
                status=status,
            ),
        )


def log_ai_response(
    logger: logging.Logger,
    *,
    request_id: str,
    model: str,
    response_text: str,
    agent_name: str | None = None,
    step_id: str | None = None,
    generic_response: str | None = None,
    owner_agent: str | None = None,
) -> None:
    response_log_content = build_response_log_content(
        response_text=response_text,
        generic_response=generic_response,
    )
    if response_log_content:
        response_status, response_summary = extract_response_preview_fields(
            response_text=response_text,
        )
        render_prompt_log_box(
            title="AI Response Preview",
            body=build_response_log_box_body(
                agent_name=agent_name,
                step_id=step_id,
                response_log_content=response_log_content,
                status=response_status,
                summary=response_summary,
                owner_agent=owner_agent or agent_name,
            ),
        )


def extract_response_preview_fields(
    *,
    response_text: str,
) -> tuple[str | None, str | None]:
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        return None, None

    if not isinstance(payload, dict):
        return None, None

    status = payload.get("status")
    result = payload.get("result")
    summary = None
    if isinstance(result, dict):
        if "summary" in result:
            summary = str(result["summary"])
        elif "final_report" in result and isinstance(result["final_report"], dict):
            final_report = result["final_report"]
            if "summary" in final_report:
                summary = str(final_report["summary"])
    return str(status) if status is not None else None, summary
