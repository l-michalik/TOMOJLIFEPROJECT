from __future__ import annotations

import re

from agentic_platform_engineer.contracts.supervisor_input import (
    JsonValue,
    RequestPriority,
    TargetEnvironment,
)
from agentic_platform_engineer.contracts.supervisor_intake import (
    OperationType,
    ParsedRequestDetails,
    SupervisorTaskClass,
)
from agentic_platform_engineer.utils.text_utils import match_group, normalize_text, read_string_value


def parse_request_details_from_text(user_request: str | None) -> ParsedRequestDetails:
    normalized_text = normalize_text(user_request)
    if normalized_text is None:
        return ParsedRequestDetails(
            service_name=None,
            target_environment=None,
            priority=None,
            operation_type=None,
            task_class=None,
            execution_params={},
            constraints=(),
        )

    operation_type = extract_operation_type(normalized_text)
    return ParsedRequestDetails(
        service_name=extract_service_name(normalized_text),
        target_environment=extract_target_environment(normalized_text),
        priority=extract_priority(normalized_text),
        operation_type=operation_type,
        task_class=classify_task(operation_type),
        execution_params=extract_execution_params(normalized_text),
        constraints=extract_constraints(normalized_text),
    )


def read_operation_type(execution_params: dict[str, JsonValue]) -> OperationType | None:
    normalized_value = read_string_value(execution_params.get("operation_type"))
    if normalized_value is None:
        return None

    try:
        return OperationType(normalized_value.lower())
    except ValueError:
        return None


def read_constraints(execution_params: dict[str, JsonValue]) -> tuple[str, ...]:
    constraints_value = execution_params.get("constraints")
    if not isinstance(constraints_value, list):
        return ()

    normalized_constraints = [
        value.strip()
        for value in constraints_value
        if isinstance(value, str) and value.strip()
    ]
    return tuple(normalized_constraints)


def service_name_is_required(parsed_details: ParsedRequestDetails) -> bool:
    return parsed_details.task_class in {
        SupervisorTaskClass.DEPLOYMENT,
        SupervisorTaskClass.CI,
    }


def classify_task(operation_type: OperationType | None) -> SupervisorTaskClass | None:
    if operation_type in {OperationType.DEPLOY, OperationType.ROLLBACK}:
        return SupervisorTaskClass.DEPLOYMENT
    if operation_type in {OperationType.INFRA_CHANGE, OperationType.INFRA_PROVISION}:
        return SupervisorTaskClass.INFRA
    if operation_type in {OperationType.PIPELINE_RUN, OperationType.PIPELINE_VALIDATE}:
        return SupervisorTaskClass.CI
    return None


def build_work_item_clarification_question(field_path: str, issue_code: object) -> str:
    from agentic_platform_engineer.contracts.supervisor_input import ValidationIssueCode

    if field_path == "work_item.operation_type":
        return "What operation should Supervisor plan for this request?"
    if field_path == "work_item.service_name":
        return "Which service should be targeted by this request?"
    if field_path == "params.target_environment":
        return "Which target environment should be used?"
    if field_path == "params.priority":
        return "What priority should be assigned to this request?"
    if issue_code is ValidationIssueCode.INVALID_TYPE:
        return f"Could you provide {field_path} in the expected format?"
    return f"What value should be provided for {field_path}?"


def extract_service_name(text: str) -> str | None:
    patterns = (
        r"\bservice\s+(?P<service>[a-z0-9][a-z0-9_-]*)\b",
        r"\bdeploy\s+(?P<service>[a-z0-9][a-z0-9_-]*)\b",
        r"\brelease\s+(?P<service>[a-z0-9][a-z0-9_-]*)\b",
        r"\brollback\s+(?P<service>[a-z0-9][a-z0-9_-]*)\b",
        r"\bpipeline\s+for\s+(?P<service>[a-z0-9][a-z0-9_-]*)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match is not None:
            return match.group("service")
    return None


def extract_target_environment(text: str) -> TargetEnvironment | None:
    if re.search(r"\b(prod|production)\b", text):
        return TargetEnvironment.PROD
    if re.search(r"\b(stage|staging)\b", text):
        return TargetEnvironment.STAGE
    if re.search(r"\b(dev|development)\b", text):
        return TargetEnvironment.DEV
    return None


def extract_priority(text: str) -> RequestPriority | None:
    if re.search(r"\burgent\b", text):
        return RequestPriority.URGENT
    if re.search(r"\bhigh\b", text):
        return RequestPriority.HIGH
    if re.search(r"\bmedium\b", text):
        return RequestPriority.MEDIUM
    if re.search(r"\blow\b", text):
        return RequestPriority.LOW
    return None


def extract_operation_type(text: str) -> OperationType | None:
    patterns: tuple[tuple[OperationType, tuple[str, ...]], ...] = (
        (OperationType.ROLLBACK, (r"\brollback\b", r"\broll back\b")),
        (OperationType.DEPLOY, (r"\bdeploy\b", r"\brelease\b")),
        (OperationType.INFRA_PROVISION, (r"\bprovision\b", r"\bcreate infrastructure\b")),
        (
            OperationType.INFRA_CHANGE,
            (r"\bconfigure\b", r"\bupdate infrastructure\b", r"\bscale\b", r"\bresize\b"),
        ),
        (
            OperationType.PIPELINE_VALIDATE,
            (r"\bvalidate pipeline\b", r"\bcheck pipeline\b", r"\bvalidate artifact\b"),
        ),
        (OperationType.PIPELINE_RUN, (r"\brun pipeline\b", r"\btrigger pipeline\b", r"\bbuild\b")),
    )
    for operation_type, operation_patterns in patterns:
        if any(re.search(pattern, text) for pattern in operation_patterns):
            return operation_type
    return None


def extract_execution_params(text: str) -> dict[str, JsonValue]:
    execution_params: dict[str, JsonValue] = {}

    version = match_group(text, r"\b(?:version|tag)\s+(?P<value>[a-z0-9._-]+)\b")
    region = match_group(text, r"\bregion\s+(?P<value>[a-z0-9-]+)\b")
    change_window = extract_change_window(text)
    rollout_mode = extract_rollout_mode(text)

    if version is not None:
        execution_params["version"] = version
    if region is not None:
        execution_params["region"] = region
    if change_window is not None:
        execution_params["change_window"] = change_window
    if rollout_mode is not None:
        execution_params["rollout_mode"] = rollout_mode

    return execution_params


def extract_constraints(text: str) -> tuple[str, ...]:
    detected_constraints: list[str] = []
    if re.search(r"\b(no downtime|zero downtime)\b", text):
        detected_constraints.append("no-downtime")
    if re.search(r"\b(outside business hours|after hours)\b", text):
        detected_constraints.append("outside-business-hours")
    if re.search(r"\bmanual approval\b", text):
        detected_constraints.append("manual-approval")
    return tuple(detected_constraints)


def extract_change_window(text: str) -> str | None:
    if re.search(r"\bbusiness hours\b", text):
        return "business-hours"
    if re.search(r"\b(outside business hours|after hours)\b", text):
        return "after-hours"
    return None


def extract_rollout_mode(text: str) -> str | None:
    if re.search(r"\bblue[- ]green\b", text):
        return "blue-green"
    if re.search(r"\bcanary\b", text):
        return "canary"
    if re.search(r"\brolling\b", text):
        return "rolling"
    return None
