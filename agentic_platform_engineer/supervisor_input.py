from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeAlias


type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]


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


@dataclass(slots=True, frozen=True)
class SupervisorInputValidation:
    normalized_input: SupervisorInput
    issues: tuple[ValidationIssue, ...]

    @property
    def is_ready_for_planning(self) -> bool:
        return self.normalized_input.intake.status is IntakeStatus.READY_FOR_PLANNING


RawJsonObject: TypeAlias = dict[str, JsonValue]


def normalize_supervisor_input(payload: RawJsonObject) -> SupervisorInputValidation:
    request_id = _read_optional_string(payload, "request_id")
    user_request = _read_optional_string(payload, "user_request")
    source = _read_optional_enum(payload, "source", RequestSource)

    params_payload = _read_optional_object(payload, "params")
    context_payload = _read_optional_object(payload, "context")

    params = SupervisorParams(
        target_environment=_read_optional_enum(params_payload, "target_environment", TargetEnvironment),
        priority=_read_optional_enum(params_payload, "priority", RequestPriority),
        execution_params=_read_json_object(params_payload, "execution_params"),
    )
    context = None
    if context_payload is not None:
        context = RequestContext(
            source_reference=_read_optional_string(context_payload, "source_reference"),
            submitted_by=_read_optional_string(context_payload, "submitted_by"),
            conversation_ref=_read_optional_string(context_payload, "conversation_ref"),
        )

    issues = _collect_validation_issues(payload, request_id, source, user_request, params)
    intake = _build_intake_assessment(issues)

    normalized_input = SupervisorInput(
        request_id=request_id,
        source=source,
        user_request=user_request,
        params=params,
        context=context,
        intake=intake,
    )
    return SupervisorInputValidation(normalized_input=normalized_input, issues=issues)


def _collect_validation_issues(
    payload: RawJsonObject,
    request_id: str | None,
    source: RequestSource | None,
    user_request: str | None,
    params: SupervisorParams,
) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []

    if request_id is None:
        issues.append(ValidationIssue("request_id", "request_id is required"))
    if source is None:
        issues.append(
            ValidationIssue("source", "source is required and must be one of: jira, chat, api")
        )
    if user_request is None:
        issues.append(ValidationIssue("user_request", "user_request is required"))
    if "params" not in payload:
        issues.append(ValidationIssue("params", "params is required"))
    elif not isinstance(payload["params"], dict):
        issues.append(ValidationIssue("params", "params must be an object"))

    if params.target_environment is None:
        issues.append(
            ValidationIssue(
                "params.target_environment",
                "target_environment is required and must be one of: dev, stage, prod",
            )
        )
    if params.priority is None:
        issues.append(
            ValidationIssue(
                "params.priority",
                "priority is required and must be one of: low, medium, high, urgent",
            )
        )

    return tuple(issues)


def _build_intake_assessment(issues: tuple[ValidationIssue, ...]) -> IntakeAssessment:
    if not issues:
        return IntakeAssessment(status=IntakeStatus.READY_FOR_PLANNING)

    missing_fields = tuple(issue.field_path for issue in issues)
    clarification_questions = tuple(_build_clarification_question(issue.field_path) for issue in issues)
    return IntakeAssessment(
        status=IntakeStatus.NEEDS_CLARIFICATION,
        missing_fields=missing_fields,
        clarification_questions=clarification_questions,
    )


def _build_clarification_question(field_path: str) -> str:
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
    return f"What value should be provided for {field_path}?"


def _read_optional_string(payload: RawJsonObject | None, field_name: str) -> str | None:
    if payload is None or field_name not in payload:
        return None

    value = payload[field_name]
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    return normalized or None


def _read_optional_enum[T: StrEnum](
    payload: RawJsonObject | None, field_name: str, enum_type: type[T]
) -> T | None:
    normalized = _read_optional_string(payload, field_name)
    if normalized is None:
        return None

    try:
        return enum_type(normalized.lower())
    except ValueError:
        return None


def _read_optional_object(payload: RawJsonObject | None, field_name: str) -> RawJsonObject | None:
    if payload is None or field_name not in payload:
        return None

    value = payload[field_name]
    if not isinstance(value, dict):
        return None
    return value


def _read_json_object(payload: RawJsonObject | None, field_name: str) -> dict[str, JsonValue]:
    if payload is None or field_name not in payload:
        return {}

    value = payload[field_name]
    if not isinstance(value, dict):
        return {}
    return value
