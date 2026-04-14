from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from contracts.task_request import ClarificationItem, TaskRequest


class SupervisorResponseStatus(str, Enum):
    NEEDS_CLARIFICATION = "needs_clarification"
    PLANNED = "planned"


class WorkflowStepStatus(str, Enum):
    PLANNED = "planned"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    BLOCKED = "blocked"


class WorkflowOverallStatus(str, Enum):
    PLANNING_COMPLETED = "planning_completed"
    WAITING_FOR_INPUT = "waiting_for_input"
    WAITING_FOR_APPROVAL = "waiting_for_approval"


class WorkflowStage(str, Enum):
    INPUT_VALIDATION = "input_validation"
    PLANNING = "planning"
    RISK_REVIEW = "risk_review"
    HUMAN_REVIEW = "human_review"
    EXECUTION = "execution"
    FINALIZATION = "finalization"


class SpecialistAgentName(str, Enum):
    DEPLOYMENT_AGENT = "DeploymentAgent"
    INFRA_AGENT = "InfraAgent"
    CI_CD_AGENT = "CI_CD_Agent"
    RISK_POLICY_AGENT = "Risk/Policy Agent"
    EXECUTION_AGENT = "Execution Agent"
    HUMAN_REVIEW_INTERFACE = "Human Review Interface"


class WorkflowPlanStep(BaseModel):
    step_id: str
    owner_agent: SpecialistAgentName
    task_description: str
    agent_instruction: str
    step_order: int
    depends_on: list[str] = Field(default_factory=list)
    expected_output_json_format: dict[str, Any] = Field(default_factory=dict)
    start_conditions: list[str] = Field(default_factory=list)
    result_handoff_condition: str
    required_input_context: dict[str, Any] = Field(default_factory=dict)
    expected_result: str
    status: WorkflowStepStatus
    risk_flags: list[str] = Field(default_factory=list)
    requires_user_approval: bool = False


class WorkflowState(BaseModel):
    workflow_id: str
    current_stage: WorkflowStage
    workflow_status: WorkflowOverallStatus
    checkpoint_id: str
    resume_token: str
    last_completed_step_id: str | None = None
    next_step_id: str | None = None


class TaskResponse(BaseModel):
    request_id: str
    status: SupervisorResponseStatus
    validation_errors: list[ClarificationItem] = Field(default_factory=list)
    normalized_request: dict[str, Any]
    model: str | None = None
    plan: list[WorkflowPlanStep] = Field(default_factory=list)
    state: WorkflowState | None = None
    confidence: float | None = None
    risk_flags: list[str] = Field(default_factory=list)
    requires_user_approval: bool = False
    answer: str | None = None

    @classmethod
    def from_clarification_request(cls, task_request: TaskRequest) -> "TaskResponse":
        return cls(
            request_id=task_request.request_id,
            status=SupervisorResponseStatus.NEEDS_CLARIFICATION,
            validation_errors=task_request.clarification_items,
            normalized_request=task_request.model_dump(mode="json"),
            state=build_waiting_for_input_state(task_request.request_id),
            answer=build_clarification_message(task_request=task_request),
        )

    @classmethod
    def from_planned_task(
        cls,
        task_request: TaskRequest,
        model: str,
        plan: list[WorkflowPlanStep],
        confidence: float,
        risk_flags: list[str],
        requires_user_approval: bool,
    ) -> "TaskResponse":
        return cls(
            request_id=task_request.request_id,
            status=SupervisorResponseStatus.PLANNED,
            validation_errors=[],
            normalized_request=task_request.model_dump(mode="json"),
            model=model,
            plan=plan,
            state=build_planned_workflow_state(
                request_id=task_request.request_id,
                plan=plan,
                requires_user_approval=requires_user_approval,
            ),
            confidence=confidence,
            risk_flags=risk_flags,
            requires_user_approval=requires_user_approval,
        )


class PlannedSupervisorOutput(BaseModel):
    plan: list[WorkflowPlanStep]
    confidence: float
    risk_flags: list[str] = Field(default_factory=list)
    requires_user_approval: bool = False


def build_waiting_for_input_state(request_id: str) -> WorkflowState:
    return WorkflowState(
        workflow_id=build_workflow_id(request_id),
        current_stage=WorkflowStage.INPUT_VALIDATION,
        workflow_status=WorkflowOverallStatus.WAITING_FOR_INPUT,
        checkpoint_id=f"{request_id}:checkpoint:input-validation",
        resume_token=f"{request_id}:resume:input-validation",
    )


def build_planned_workflow_state(
    request_id: str, plan: list[WorkflowPlanStep], requires_user_approval: bool
) -> WorkflowState:
    next_step_id = plan[0].step_id if plan else None
    workflow_status = WorkflowOverallStatus.PLANNING_COMPLETED
    current_stage = WorkflowStage.RISK_REVIEW

    if requires_user_approval:
        workflow_status = WorkflowOverallStatus.WAITING_FOR_APPROVAL
        current_stage = WorkflowStage.HUMAN_REVIEW

    return WorkflowState(
        workflow_id=build_workflow_id(request_id),
        current_stage=current_stage,
        workflow_status=workflow_status,
        checkpoint_id=f"{request_id}:checkpoint:planning",
        resume_token=f"{request_id}:resume:planning",
        last_completed_step_id=None,
        next_step_id=next_step_id,
    )


def build_workflow_id(request_id: str) -> str:
    return f"workflow-{request_id}"


def build_clarification_message(task_request: TaskRequest) -> str:
    clarification_lines = [
        "Request requires clarification before planning.",
        "",
        "Missing or incomplete fields:",
    ]
    for item in task_request.clarification_items:
        clarification_lines.append(f"- {item.field_name}: {item.reason}")
    return "\n".join(clarification_lines)
