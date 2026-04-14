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
