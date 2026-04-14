from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from agentic_platform_engineer.contracts.supervisor_input import IntakeAssessment, JsonValue


class PlanStatus(StrEnum):
    PLANNED = "planned"
    NEEDS_CLARIFICATION = "needs_clarification"


class PlanStepStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class TargetAgent(StrEnum):
    DEPLOYMENT = "DeploymentAgent"
    INFRA = "InfraAgent"
    CI_CD = "CI_CD_Agent"


@dataclass(slots=True, frozen=True)
class PlanStep:
    step_id: str
    name: str
    target_agent: TargetAgent
    instruction: str
    expected_response_format: dict[str, JsonValue]
    start_condition: str
    dependencies: tuple[str, ...] = ()
    aggregation_condition: str = ""
    status: PlanStepStatus = PlanStepStatus.PENDING


@dataclass(slots=True, frozen=True)
class SupervisorPlan:
    request_id: str | None
    status: PlanStatus
    steps: tuple[PlanStep, ...] = ()


@dataclass(slots=True, frozen=True)
class SupervisorPlanBuildResult:
    plan: SupervisorPlan
    intake: IntakeAssessment
    planning_block_reason: str | None = None
    planned_actions_hint: tuple[str, ...] = field(default_factory=tuple)
