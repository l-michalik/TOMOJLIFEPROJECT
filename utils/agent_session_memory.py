from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from contracts.agent_session_memory import (
    AgentSessionMemory,
    SessionCommandRecord,
    SessionIntermediateResult,
)
from contracts.task_request import TaskRequest
from contracts.task_response import WorkflowPlanStep, WorkflowStepState

MAX_SESSION_LOG_LINES = 8
MAX_SESSION_COMMANDS = 5


def build_initial_session_memory(
    *,
    step: WorkflowPlanStep,
    task_request: TaskRequest,
    dependency_step_states: list[WorkflowStepState],
) -> AgentSessionMemory:
    return AgentSessionMemory(
        request_id=task_request.request_id,
        step_id=step.step_id,
        owner_agent=step.owner_agent.value,
        current_task_context=build_current_task_context(step, task_request),
        recent_commands=collect_recent_commands(dependency_step_states),
        intermediate_results=collect_intermediate_results(dependency_step_states),
        environment_logs=collect_environment_logs(dependency_step_states),
        technical_notes=build_technical_notes(step, task_request),
        updated_at=utc_now(),
    )


def finalize_session_memory(
    initial_memory: AgentSessionMemory,
    raw_response: dict[str, Any],
) -> AgentSessionMemory:
    session_memory = initial_memory.model_copy(deep=True)
    response_logs = normalize_text_list(raw_response.get("logs"))
    execution_details = normalize_dict(raw_response.get("execution_details"))
    result = normalize_dict(raw_response.get("result"))

    session_memory.recent_commands = deduplicate_command_records(
        session_memory.recent_commands + extract_commands_from_execution_details(execution_details)
    )[:MAX_SESSION_COMMANDS]
    session_memory.environment_logs = deduplicate_text_list(
        session_memory.environment_logs + response_logs
    )[-MAX_SESSION_LOG_LINES:]
    if result:
        session_memory.intermediate_results.append(
            SessionIntermediateResult(
                source_step_id=initial_memory.step_id,
                summary=build_result_summary(result),
                payload=build_compact_result_payload(result),
            )
        )
    session_memory.intermediate_results = deduplicate_intermediate_results(
        session_memory.intermediate_results
    )
    session_memory.technical_notes = {
        **session_memory.technical_notes,
        "latest_step_status": raw_response.get("status"),
        "latest_execution_details": execution_details,
    }
    session_memory.updated_at = utc_now()
    return session_memory


def build_current_task_context(
    step: WorkflowPlanStep,
    task_request: TaskRequest,
) -> dict[str, Any]:
    work_item = task_request.standardized_work_item
    return {
        "task_description": step.task_description,
        "agent_instruction": step.agent_instruction,
        "expected_result": step.expected_result,
        "service_name": work_item.service_name,
        "target_environment": work_item.target_environment.value,
        "task_type": step.task_type.value,
        "operation_type": work_item.operation_type.value if work_item.operation_type else None,
    }


def build_technical_notes(
    step: WorkflowPlanStep,
    task_request: TaskRequest,
) -> dict[str, Any]:
    return {
        "required_input_context": deepcopy(step.required_input_context),
        "execution_constraints": list(task_request.standardized_work_item.constraints)
        + list(step.start_conditions),
        "risk_flags": list(step.risk_flags),
        "depends_on": list(step.depends_on),
    }


def collect_recent_commands(
    dependency_step_states: list[WorkflowStepState],
) -> list[SessionCommandRecord]:
    commands: list[SessionCommandRecord] = []
    for dependency_step in dependency_step_states:
        commands.extend(
            extract_commands_from_execution_details(dependency_step.execution_details)
        )
    return deduplicate_command_records(commands)[-MAX_SESSION_COMMANDS:]


def collect_intermediate_results(
    dependency_step_states: list[WorkflowStepState],
) -> list[SessionIntermediateResult]:
    results: list[SessionIntermediateResult] = []
    for dependency_step in dependency_step_states:
        if not dependency_step.response:
            continue
        results.append(
            SessionIntermediateResult(
                source_step_id=dependency_step.step_id,
                summary=build_result_summary(dependency_step.response),
                payload=build_compact_result_payload(dependency_step.response),
            )
        )
    return results


def collect_environment_logs(
    dependency_step_states: list[WorkflowStepState],
) -> list[str]:
    logs: list[str] = []
    for dependency_step in dependency_step_states:
        logs.extend(dependency_step.logs[-2:])
    return deduplicate_text_list(logs)[-MAX_SESSION_LOG_LINES:]


def extract_commands_from_execution_details(
    execution_details: dict[str, Any],
) -> list[SessionCommandRecord]:
    command_like_values: list[SessionCommandRecord] = []
    for key in ("commands", "recent_commands", "tool_calls", "shell_commands"):
        raw_value = execution_details.get(key)
        if isinstance(raw_value, list):
            for item in raw_value:
                summary = normalize_command_summary(item)
                if summary:
                    command_like_values.append(SessionCommandRecord(summary=summary))
    single_command = normalize_command_summary(execution_details.get("command"))
    if single_command:
        command_like_values.append(SessionCommandRecord(summary=single_command))
    return command_like_values


def normalize_command_summary(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        command = value.get("command") or value.get("summary") or value.get("name")
        if isinstance(command, str) and command.strip():
            return command.strip()
    return None


def build_result_summary(result: dict[str, Any]) -> str:
    summary = result.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    findings = result.get("findings")
    if isinstance(findings, list) and findings:
        return str(findings[0])
    return "Intermediate result available."


def build_compact_result_payload(result: dict[str, Any]) -> dict[str, Any]:
    compact_payload: dict[str, Any] = {}
    for key in ("summary", "findings", "decisions", "execution_handoff", "proposed_actions"):
        if key in result:
            compact_payload[key] = deepcopy(result[key])
    return compact_payload


def deduplicate_command_records(
    values: list[SessionCommandRecord],
) -> list[SessionCommandRecord]:
    normalized_values: list[SessionCommandRecord] = []
    seen_summaries: set[str] = set()
    for value in values:
        if value.summary in seen_summaries:
            continue
        seen_summaries.add(value.summary)
        normalized_values.append(value)
    return normalized_values


def deduplicate_intermediate_results(
    values: list[SessionIntermediateResult],
) -> list[SessionIntermediateResult]:
    normalized_values: list[SessionIntermediateResult] = []
    seen_keys: set[tuple[str, str]] = set()
    for value in values:
        dedupe_key = (value.source_step_id, value.summary)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        normalized_values.append(value)
    return normalized_values


def normalize_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def deduplicate_text_list(values: list[str]) -> list[str]:
    normalized_values: list[str] = []
    seen_values: set[str] = set()
    for value in values:
        if value in seen_values:
            continue
        seen_values.add(value)
        normalized_values.append(value)
    return normalized_values


def normalize_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    return {}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
