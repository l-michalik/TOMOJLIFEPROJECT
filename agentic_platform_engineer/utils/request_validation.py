from __future__ import annotations

from enum import StrEnum

from agentic_platform_engineer.contracts.supervisor_input import (
    JsonValue,
    RawJsonObject,
    RequestContext,
    RequestPriority,
    RequestSource,
    SupervisorParams,
    TargetEnvironment,
    ValidationIssue,
    ValidationIssueCode,
)
from agentic_platform_engineer.utils.json_utils import is_json_value
from agentic_platform_engineer.utils.object_utils import build_field_path, get_object


def collect_validation_issues(payload: RawJsonObject) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    issues.extend(validate_required_string(payload, "request_id"))
    issues.extend(validate_required_enum(payload, "source", RequestSource))
    issues.extend(validate_required_string(payload, "user_request"))
    issues.extend(_validate_params(payload))
    issues.extend(_validate_context(payload))
    return tuple(issues)


def build_supervisor_params(payload: RawJsonObject) -> SupervisorParams:
    params_payload = get_object(payload, "params")
    return SupervisorParams(
        target_environment=normalize_enum(params_payload, "target_environment", TargetEnvironment),
        priority=normalize_enum(params_payload, "priority", RequestPriority),
        execution_params=normalize_execution_params(params_payload),
    )


def build_request_context(payload: RawJsonObject) -> RequestContext | None:
    context_payload = get_object(payload, "context")
    if context_payload is None:
        return None

    return RequestContext(
        source_reference=normalize_optional_string(context_payload, "source_reference"),
        submitted_by=normalize_optional_string(context_payload, "submitted_by"),
        conversation_ref=normalize_optional_string(context_payload, "conversation_ref"),
    )


def normalize_required_string(payload: RawJsonObject, field_name: str) -> str | None:
    return normalize_optional_string(payload, field_name)


def normalize_optional_string(payload: RawJsonObject | None, field_name: str) -> str | None:
    if payload is None or field_name not in payload:
        return None

    value = payload[field_name]
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    return normalized or None


def normalize_execution_params(payload: RawJsonObject | None) -> dict[str, JsonValue]:
    execution_params = get_object(payload, "execution_params")
    if execution_params is None:
        return {}

    if not all(isinstance(key, str) and is_json_value(value) for key, value in execution_params.items()):
        return {}
    return execution_params


def validate_required_string(
    payload: RawJsonObject,
    field_name: str,
    *,
    parent_path: str | None = None,
) -> list[ValidationIssue]:
    field_path = build_field_path(field_name, parent_path)
    if field_name not in payload:
        return [
            ValidationIssue(
                field_path,
                f"{field_name} is required",
                ValidationIssueCode.MISSING_REQUIRED,
            )
        ]

    value = payload[field_name]
    if not isinstance(value, str):
        return [
            ValidationIssue(
                field_path,
                f"{field_name} must be a string",
                ValidationIssueCode.INVALID_TYPE,
            )
        ]

    if not value.strip():
        return [
            ValidationIssue(
                field_path,
                f"{field_name} must not be blank",
                ValidationIssueCode.MISSING_REQUIRED,
            )
        ]

    return []


def validate_optional_string(
    payload: RawJsonObject,
    field_name: str,
    *,
    parent_path: str | None = None,
) -> list[ValidationIssue]:
    if field_name not in payload:
        return []

    value = payload[field_name]
    if isinstance(value, str):
        return []

    return [
        ValidationIssue(
            build_field_path(field_name, parent_path),
            f"{field_name} must be a string",
            ValidationIssueCode.INVALID_TYPE,
        )
    ]


def validate_required_enum[T: StrEnum](
    payload: RawJsonObject,
    field_name: str,
    enum_type: type[T],
    *,
    parent_path: str | None = None,
) -> list[ValidationIssue]:
    string_issues = validate_required_string(payload, field_name, parent_path=parent_path)
    if string_issues:
        return string_issues

    normalized_value = normalize_optional_string(payload, field_name)
    assert normalized_value is not None

    try:
        enum_type(normalized_value.lower())
    except ValueError:
        allowed_values = ", ".join(member.value for member in enum_type)
        return [
            ValidationIssue(
                build_field_path(field_name, parent_path),
                f"{field_name} must be one of: {allowed_values}",
                ValidationIssueCode.UNSUPPORTED_VALUE,
            )
        ]

    return []


def normalize_enum[T: StrEnum](
    payload: RawJsonObject | None,
    field_name: str,
    enum_type: type[T],
) -> T | None:
    normalized = normalize_optional_string(payload, field_name)
    if normalized is None:
        return None

    try:
        return enum_type(normalized.lower())
    except ValueError:
        return None


def build_input_clarification_question(field_path: str, issue_code: ValidationIssueCode) -> str:
    if field_path == "request_id":
        return "What is the request identifier for this task?"
    if field_path == "source":
        return "What is the source of this request: Jira, chat, or API?"
    if field_path == "user_request":
        return "What task should be performed?"
    if field_path == "params":
        return "What structured execution parameters should be attached to this request?"
    if field_path == "params.target_environment":
        return "Which target environment should be used?"
    if field_path == "params.priority":
        return "What priority should be assigned to this request?"
    if field_path == "params.execution_params":
        return "Which execution parameters should be provided as a structured object?"
    if field_path == "context":
        return "Which request context should be provided as a structured object?"
    if issue_code is ValidationIssueCode.INVALID_TYPE:
        return f"Could you provide {field_path} in the expected format?"
    return f"What value should be provided for {field_path}?"


def _validate_params(payload: RawJsonObject) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    params_payload = payload.get("params")

    if "params" not in payload:
        issues.append(
            ValidationIssue(
                "params",
                "params is required",
                ValidationIssueCode.MISSING_REQUIRED,
            )
        )
        return issues

    if not isinstance(params_payload, dict):
        issues.append(
            ValidationIssue(
                "params",
                "params must be an object",
                ValidationIssueCode.INVALID_TYPE,
            )
        )
        return issues

    issues.extend(
        validate_required_enum(
            params_payload,
            "target_environment",
            TargetEnvironment,
            parent_path="params",
        )
    )
    issues.extend(
        validate_required_enum(
            params_payload,
            "priority",
            RequestPriority,
            parent_path="params",
        )
    )
    issues.extend(_validate_execution_params(params_payload))
    return issues


def _validate_context(payload: RawJsonObject) -> list[ValidationIssue]:
    if "context" not in payload:
        return []

    context_payload = payload["context"]
    if not isinstance(context_payload, dict):
        return [
            ValidationIssue(
                "context",
                "context must be an object",
                ValidationIssueCode.INVALID_TYPE,
            )
        ]

    issues: list[ValidationIssue] = []
    for field_name in ("source_reference", "submitted_by", "conversation_ref"):
        issues.extend(validate_optional_string(context_payload, field_name, parent_path="context"))
    return issues


def _validate_execution_params(params_payload: RawJsonObject) -> list[ValidationIssue]:
    if "execution_params" not in params_payload:
        return []

    execution_params = params_payload["execution_params"]
    if not isinstance(execution_params, dict):
        return [
            ValidationIssue(
                "params.execution_params",
                "execution_params must be an object",
                ValidationIssueCode.INVALID_TYPE,
            )
        ]

    issues: list[ValidationIssue] = []
    for key, value in execution_params.items():
        if isinstance(key, str) and is_json_value(value):
            continue

        issues.append(
            ValidationIssue(
                f"params.execution_params.{key}",
                "execution_params values must be JSON-compatible",
                ValidationIssueCode.INVALID_JSON_VALUE,
            )
        )
    return issues
