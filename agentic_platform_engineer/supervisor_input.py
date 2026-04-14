from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeAlias


type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
RawJsonObject: TypeAlias = dict[str, JsonValue]


class RequestSource(StrEnum):
    JIRA = "jira"
    CHAT = "chat"
    API = "api"


class TargetEnvironment(StrEnum):
    DEV = "dev"
    STAGE = "stage"
    PROD = "prod"


class RequestPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class IntakeStatus(StrEnum):
    READY_FOR_PLANNING = "ready_for_planning"
    NEEDS_CLARIFICATION = "needs_clarification"


class ValidationIssueCode(StrEnum):
    MISSING_REQUIRED = "missing_required"
    INVALID_TYPE = "invalid_type"
    UNSUPPORTED_VALUE = "unsupported_value"
    INVALID_JSON_VALUE = "invalid_json_value"


@dataclass(slots=True, frozen=True)
class RequestContext:
    source_reference: str | None = None
    submitted_by: str | None = None
    conversation_ref: str | None = None


@dataclass(slots=True, frozen=True)
class SupervisorParams:
    target_environment: TargetEnvironment | None
    priority: RequestPriority | None
    execution_params: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class IntakeAssessment:
    status: IntakeStatus
    missing_fields: tuple[str, ...] = ()
    invalid_fields: tuple[str, ...] = ()
    clarification_questions: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class SupervisorInput:
    request_id: str | None
    source: RequestSource | None
    user_request: str | None
    params: SupervisorParams
    context: RequestContext | None = None
    intake: IntakeAssessment = field(
        default_factory=lambda: IntakeAssessment(status=IntakeStatus.NEEDS_CLARIFICATION)
    )


@dataclass(slots=True, frozen=True)
class ValidationIssue:
    field_path: str
    message: str
    code: ValidationIssueCode

    @property
    def blocks_planning(self) -> bool:
        return self.code in {
            ValidationIssueCode.MISSING_REQUIRED,
            ValidationIssueCode.INVALID_TYPE,
            ValidationIssueCode.UNSUPPORTED_VALUE,
            ValidationIssueCode.INVALID_JSON_VALUE,
        }


@dataclass(slots=True, frozen=True)
class SupervisorInputValidation:
    normalized_input: SupervisorInput
    issues: tuple[ValidationIssue, ...]

    @property
    def is_ready_for_planning(self) -> bool:
        return self.normalized_input.intake.status is IntakeStatus.READY_FOR_PLANNING


def normalize_supervisor_input(payload: RawJsonObject) -> SupervisorInputValidation:
    issues = _collect_validation_issues(payload)

    normalized_input = SupervisorInput(
        request_id=_normalize_required_string(payload, "request_id"),
        source=_normalize_enum(payload, "source", RequestSource),
        user_request=_normalize_required_string(payload, "user_request"),
        params=_normalize_params(payload),
        context=_normalize_context(payload),
        intake=_build_intake_assessment(issues),
    )
    return SupervisorInputValidation(normalized_input=normalized_input, issues=issues)


def _collect_validation_issues(payload: RawJsonObject) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    issues.extend(_validate_required_string(payload, "request_id"))
    issues.extend(_validate_required_enum(payload, "source", RequestSource))
    issues.extend(_validate_required_string(payload, "user_request"))
    issues.extend(_validate_params(payload))
    issues.extend(_validate_context(payload))
    return tuple(issues)


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
        _validate_required_enum(
            params_payload,
            "target_environment",
            TargetEnvironment,
            parent_path="params",
        )
    )
    issues.extend(
        _validate_required_enum(
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
        issues.extend(_validate_optional_string(context_payload, field_name, parent_path="context"))
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
        if isinstance(key, str) and _is_json_value(value):
            continue

        issues.append(
            ValidationIssue(
                f"params.execution_params.{key}",
                "execution_params values must be JSON-compatible",
                ValidationIssueCode.INVALID_JSON_VALUE,
            )
        )
    return issues


def _build_intake_assessment(issues: tuple[ValidationIssue, ...]) -> IntakeAssessment:
    blocking_issues = tuple(issue for issue in issues if issue.blocks_planning)
    if not blocking_issues:
        return IntakeAssessment(status=IntakeStatus.READY_FOR_PLANNING)

    missing_fields = tuple(
        issue.field_path for issue in blocking_issues if issue.code is ValidationIssueCode.MISSING_REQUIRED
    )
    invalid_fields = tuple(
        issue.field_path for issue in blocking_issues if issue.code is not ValidationIssueCode.MISSING_REQUIRED
    )
    clarification_questions = tuple(
        _build_clarification_question(issue.field_path, issue.code) for issue in blocking_issues
    )
    return IntakeAssessment(
        status=IntakeStatus.NEEDS_CLARIFICATION,
        missing_fields=missing_fields,
        invalid_fields=invalid_fields,
        clarification_questions=clarification_questions,
    )


def _build_clarification_question(field_path: str, issue_code: ValidationIssueCode) -> str:
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


def _normalize_params(payload: RawJsonObject) -> SupervisorParams:
    params_payload = _get_object(payload, "params")
    return SupervisorParams(
        target_environment=_normalize_enum(params_payload, "target_environment", TargetEnvironment),
        priority=_normalize_enum(params_payload, "priority", RequestPriority),
        execution_params=_normalize_execution_params(params_payload),
    )


def _normalize_context(payload: RawJsonObject) -> RequestContext | None:
    context_payload = _get_object(payload, "context")
    if context_payload is None:
        return None

    return RequestContext(
        source_reference=_normalize_optional_string(context_payload, "source_reference"),
        submitted_by=_normalize_optional_string(context_payload, "submitted_by"),
        conversation_ref=_normalize_optional_string(context_payload, "conversation_ref"),
    )


def _normalize_execution_params(payload: RawJsonObject | None) -> dict[str, JsonValue]:
    execution_params = _get_object(payload, "execution_params")
    if execution_params is None:
        return {}

    if not all(isinstance(key, str) and _is_json_value(value) for key, value in execution_params.items()):
        return {}
    return execution_params


def _validate_required_string(
    payload: RawJsonObject,
    field_name: str,
    *,
    parent_path: str | None = None,
) -> list[ValidationIssue]:
    field_path = _field_path(field_name, parent_path)
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


def _validate_optional_string(
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
            _field_path(field_name, parent_path),
            f"{field_name} must be a string",
            ValidationIssueCode.INVALID_TYPE,
        )
    ]


def _validate_required_enum[T: StrEnum](
    payload: RawJsonObject,
    field_name: str,
    enum_type: type[T],
    *,
    parent_path: str | None = None,
) -> list[ValidationIssue]:
    string_issues = _validate_required_string(payload, field_name, parent_path=parent_path)
    if string_issues:
        return string_issues

    normalized_value = _normalize_optional_string(payload, field_name)
    assert normalized_value is not None

    try:
        enum_type(normalized_value.lower())
    except ValueError:
        allowed_values = ", ".join(member.value for member in enum_type)
        return [
            ValidationIssue(
                _field_path(field_name, parent_path),
                f"{field_name} must be one of: {allowed_values}",
                ValidationIssueCode.UNSUPPORTED_VALUE,
            )
        ]

    return []


def _normalize_required_string(payload: RawJsonObject, field_name: str) -> str | None:
    return _normalize_optional_string(payload, field_name)


def _normalize_optional_string(payload: RawJsonObject | None, field_name: str) -> str | None:
    if payload is None or field_name not in payload:
        return None

    value = payload[field_name]
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    return normalized or None


def _normalize_enum[T: StrEnum](
    payload: RawJsonObject | None,
    field_name: str,
    enum_type: type[T],
) -> T | None:
    normalized = _normalize_optional_string(payload, field_name)
    if normalized is None:
        return None

    try:
        return enum_type(normalized.lower())
    except ValueError:
        return None


def _get_object(payload: RawJsonObject | None, field_name: str) -> RawJsonObject | None:
    if payload is None or field_name not in payload:
        return None

    value = payload[field_name]
    if not isinstance(value, dict):
        return None
    return value


def _field_path(field_name: str, parent_path: str | None) -> str:
    if parent_path is None:
        return field_name
    return f"{parent_path}.{field_name}"


def _is_json_value(value: object) -> bool:
    if value is None or isinstance(value, str | int | float | bool):
        return True
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_value(item) for key, item in value.items())
    return False
