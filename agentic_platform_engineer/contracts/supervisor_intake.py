from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from agentic_platform_engineer.contracts.supervisor_input import (
    IntakeAssessment,
    IntakeStatus,
    JsonValue,
    RawJsonObject,
    RequestContext,
    RequestPriority,
    RequestSource,
    SupervisorInput,
    TargetEnvironment,
    ValidationIssue,
)


class SupervisorTaskClass(StrEnum):
    DEPLOYMENT = "deployment"
    INFRA = "infra"
    CI = "ci"


class OperationType(StrEnum):
    DEPLOY = "deploy"
    ROLLBACK = "rollback"
    INFRA_CHANGE = "infra_change"
    INFRA_PROVISION = "infra_provision"
    PIPELINE_RUN = "pipeline_run"
    PIPELINE_VALIDATE = "pipeline_validate"


@dataclass(slots=True, frozen=True)
class ParsedRequestDetails:
    service_name: str | None
    target_environment: TargetEnvironment | None
    priority: RequestPriority | None
    operation_type: OperationType | None
    task_class: SupervisorTaskClass | None
    execution_params: dict[str, JsonValue]
    constraints: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class SupervisorWorkItem:
    request_id: str | None
    source: RequestSource | None
    user_request: str | None
    service_name: str | None
    target_environment: TargetEnvironment | None
    priority: RequestPriority | None
    operation_type: OperationType | None
    task_class: SupervisorTaskClass | None
    execution_params: dict[str, JsonValue]
    constraints: tuple[str, ...]
    context: RequestContext | None
    intake: IntakeAssessment


@dataclass(slots=True, frozen=True)
class SupervisorWorkItemBuildResult:
    normalized_input: SupervisorInput
    work_item: SupervisorWorkItem
    issues: tuple[ValidationIssue, ...]
    enriched_payload: RawJsonObject

    @property
    def is_ready_for_planning(self) -> bool:
        return self.work_item.intake.status is IntakeStatus.READY_FOR_PLANNING
