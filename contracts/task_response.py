from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from contracts.agent_session_memory import AgentSessionMemory
from contracts.agent_input import AgentTaskType
from contracts.agent_output import (
    AgentAnalysisDetail,
    AgentArtifactReference,
    AgentTechnicalError,
    SupervisorAggregationPayload,
)
from contracts.final_report import WorkflowFinalReport
from contracts.task_request import ClarificationItem, RequestSource, TaskRequest
from contracts.workflow_aggregation import WorkflowAggregationSummary


class SupervisorResponseStatus(str, Enum):
    NEEDS_CLARIFICATION = "needs_clarification"
    PLANNED = "planned"


class WorkflowStepStatus(str, Enum):
    PLANNED = "planned"
    DELEGATED = "delegated"
    WAITING_FOR_RESULTS = "waiting_for_results"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class WorkflowLifecycleStatus(str, Enum):
    RECEIVED = "received"
    NEEDS_CLARIFICATION = "needs_clarification"
    PLANNED = "planned"
    DELEGATED = "delegated"
    WAITING_FOR_RESULTS = "waiting_for_results"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class WorkflowStage(str, Enum):
    RECEIVED = "received"
    INPUT_VALIDATION = "input_validation"
    PLANNING = "planning"
    DELEGATION = "delegation"
    SPECIALIST_ANALYSIS = "specialist_analysis"
    RISK_REVIEW = "risk_review"
    HUMAN_REVIEW = "human_review"
    EXECUTION = "execution"
    FINALIZATION = "finalization"
    COMPLETED = "completed"


class WorkflowDecisionType(str, Enum):
    STATE_TRANSITION = "state_transition"
    CLARIFICATION_REQUESTED = "clarification_requested"
    PLAN_CREATED = "plan_created"
    APPROVAL_REQUIRED = "approval_required"
    POLICY_REVIEW_PENDING = "policy_review_pending"


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
    task_type: AgentTaskType
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


class WorkflowStepState(BaseModel):
    step_id: str
    step_order: int
    owner_agent: SpecialistAgentName
    task_description: str
    status: WorkflowStepStatus
    depends_on: list[str] = Field(default_factory=list)
    response: dict[str, Any] | None = None
    logs: list[str] = Field(default_factory=list)
    analysis_details: list[AgentAnalysisDetail] = Field(default_factory=list)
    recommended_actions: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[AgentArtifactReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    technical_errors: list[AgentTechnicalError] = Field(default_factory=list)
    supervisor_data: SupervisorAggregationPayload = Field(
        default_factory=SupervisorAggregationPayload
    )
    execution_details: dict[str, Any] = Field(default_factory=dict)
    session_memory: AgentSessionMemory | None = None
    error_details: dict[str, Any] | None = None
    status_reason: str | None = None
    updated_at: datetime


class WorkflowDecisionRecord(BaseModel):
    decision_id: str
    decision_type: WorkflowDecisionType
    summary: str
    actor: str
    related_step_id: str | None = None
    previous_status: WorkflowLifecycleStatus | None = None
    new_status: WorkflowLifecycleStatus
    created_at: datetime


class WorkflowResumeData(BaseModel):
    checkpoint_id: str
    resume_token: str
    last_completed_step_id: str | None = None
    next_step_id: str | None = None
    delegated_step_ids: list[str] = Field(default_factory=list)
    waiting_step_ids: list[str] = Field(default_factory=list)


class WorkflowTimestamps(BaseModel):
    received_at: datetime
    updated_at: datetime
    clarification_requested_at: datetime | None = None
    planned_at: datetime | None = None
    delegated_at: datetime | None = None
    waiting_for_results_at: datetime | None = None
    waiting_for_approval_at: datetime | None = None
    executing_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    blocked_at: datetime | None = None


class WorkflowState(BaseModel):
    request_id: str
    source: RequestSource
    workflow_id: str
    current_stage: WorkflowStage
    lifecycle_status: WorkflowLifecycleStatus
    plan_steps: list[WorkflowStepState] = Field(default_factory=list)
    aggregation: WorkflowAggregationSummary | None = None
    decision_history: list[WorkflowDecisionRecord] = Field(default_factory=list)
    resume_data: WorkflowResumeData
    timestamps: WorkflowTimestamps


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
    final_report: WorkflowFinalReport | None = None
    answer: str | None = None

    @classmethod
    def from_clarification_request(cls, task_request: TaskRequest) -> "TaskResponse":
        return cls(
            request_id=task_request.request_id,
            status=SupervisorResponseStatus.NEEDS_CLARIFICATION,
            validation_errors=task_request.clarification_items,
            normalized_request=task_request.model_dump(mode="json"),
            state=build_waiting_for_input_state(task_request),
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
        delegation_result: dict[str, Any] | None = None,
    ) -> "TaskResponse":
        return cls(
            request_id=task_request.request_id,
            status=SupervisorResponseStatus.PLANNED,
            validation_errors=[],
            normalized_request=task_request.model_dump(mode="json"),
            model=model,
            plan=plan,
            state=build_planned_workflow_state(
                task_request=task_request,
                plan=plan,
                requires_user_approval=requires_user_approval,
                delegation_result=delegation_result,
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


def build_waiting_for_input_state(task_request: TaskRequest) -> WorkflowState:
    now = utc_now()
    return WorkflowState(
        request_id=task_request.request_id,
        source=task_request.source,
        workflow_id=build_workflow_id(task_request.request_id),
        current_stage=WorkflowStage.INPUT_VALIDATION,
        lifecycle_status=WorkflowLifecycleStatus.NEEDS_CLARIFICATION,
        plan_steps=[],
        decision_history=[
            build_decision_record(
                decision_id="DEC-1",
                decision_type=WorkflowDecisionType.STATE_TRANSITION,
                summary="Request received by Supervisor.",
                actor="Supervisor",
                previous_status=None,
                new_status=WorkflowLifecycleStatus.RECEIVED,
                created_at=now,
            ),
            build_decision_record(
                decision_id="DEC-2",
                decision_type=WorkflowDecisionType.CLARIFICATION_REQUESTED,
                summary="Request requires clarification before planning.",
                actor="Supervisor",
                previous_status=WorkflowLifecycleStatus.RECEIVED,
                new_status=WorkflowLifecycleStatus.NEEDS_CLARIFICATION,
                created_at=now,
            ),
        ],
        resume_data=WorkflowResumeData(
            checkpoint_id=f"{task_request.request_id}:checkpoint:input-validation",
            resume_token=f"{task_request.request_id}:resume:input-validation",
        ),
        timestamps=WorkflowTimestamps(
            received_at=now,
            updated_at=now,
            clarification_requested_at=now,
        ),
    )


def build_planned_workflow_state(
    task_request: TaskRequest,
    plan: list[WorkflowPlanStep],
    requires_user_approval: bool,
    delegation_result: dict[str, Any] | None = None,
) -> WorkflowState:
    now = utc_now()
    next_step_id = plan[0].step_id if plan else None
    lifecycle_status = WorkflowLifecycleStatus.PLANNED
    current_stage = WorkflowStage.PLANNING
    decision_history = [
        build_decision_record(
            decision_id="DEC-1",
            decision_type=WorkflowDecisionType.STATE_TRANSITION,
            summary="Request received by Supervisor.",
            actor="Supervisor",
            previous_status=None,
            new_status=WorkflowLifecycleStatus.RECEIVED,
            created_at=now,
        ),
        build_decision_record(
            decision_id="DEC-2",
            decision_type=WorkflowDecisionType.PLAN_CREATED,
            summary="Workflow plan created and stored in state.",
            actor="Supervisor",
            previous_status=WorkflowLifecycleStatus.RECEIVED,
            new_status=WorkflowLifecycleStatus.PLANNED,
            created_at=now,
        ),
    ]
    waiting_step_ids = [step.step_id for step in plan if step.status != WorkflowStepStatus.PLANNED]

    if requires_user_approval:
        lifecycle_status = WorkflowLifecycleStatus.WAITING_FOR_APPROVAL
        current_stage = WorkflowStage.HUMAN_REVIEW
        decision_history.append(
            build_decision_record(
                decision_id="DEC-3",
                decision_type=WorkflowDecisionType.APPROVAL_REQUIRED,
                summary="Workflow paused pending human approval.",
                actor="Supervisor",
                previous_status=WorkflowLifecycleStatus.PLANNED,
                new_status=WorkflowLifecycleStatus.WAITING_FOR_APPROVAL,
                created_at=now,
                related_step_id=find_first_step_id_by_status(
                    plan=plan,
                    target_status=WorkflowStepStatus.WAITING_FOR_APPROVAL,
                ),
            )
        )
    else:
        current_stage = WorkflowStage.DELEGATION
        decision_history.append(
            build_decision_record(
                decision_id="DEC-3",
                decision_type=WorkflowDecisionType.POLICY_REVIEW_PENDING,
                summary="Workflow is planned and ready for delegation and result collection.",
                actor="Supervisor",
                previous_status=WorkflowLifecycleStatus.PLANNED,
                new_status=WorkflowLifecycleStatus.PLANNED,
                created_at=now,
            )
        )

    if delegation_result:
        lifecycle_status = delegation_result["lifecycle_status"]
        current_stage = delegation_result["current_stage"]
        waiting_step_ids = delegation_result["waiting_step_ids"]
        next_step_id = delegation_result["next_step_id"]
        decision_history.append(
            build_decision_record(
                decision_id=f"DEC-{len(decision_history) + 1}",
                decision_type=WorkflowDecisionType.STATE_TRANSITION,
                summary="Workflow delegation executed against specialist steps.",
                actor="Supervisor",
                previous_status=WorkflowLifecycleStatus.PLANNED,
                new_status=lifecycle_status,
                created_at=now,
                related_step_id=delegation_result["last_completed_step_id"],
            )
        )

    return WorkflowState(
        request_id=task_request.request_id,
        source=task_request.source,
        workflow_id=build_workflow_id(task_request.request_id),
        current_stage=current_stage,
        lifecycle_status=lifecycle_status,
        plan_steps=delegation_result["step_states"] if delegation_result else build_step_states(plan=plan, updated_at=now),
        aggregation=delegation_result["aggregation"] if delegation_result else None,
        decision_history=decision_history,
        resume_data=WorkflowResumeData(
            checkpoint_id=f"{task_request.request_id}:checkpoint:delegation"
            if delegation_result
            else f"{task_request.request_id}:checkpoint:planning",
            resume_token=f"{task_request.request_id}:resume:delegation"
            if delegation_result
            else f"{task_request.request_id}:resume:planning",
            last_completed_step_id=delegation_result["last_completed_step_id"]
            if delegation_result
            else None,
            next_step_id=next_step_id,
            delegated_step_ids=delegation_result["delegated_step_ids"]
            if delegation_result
            else [],
            waiting_step_ids=waiting_step_ids,
        ),
        timestamps=build_planned_timestamps(
            now=now,
            requires_user_approval=requires_user_approval,
            delegation_result=delegation_result,
        ),
    )


def build_workflow_id(request_id: str) -> str:
    return f"workflow-{request_id}"


def build_step_states(
    plan: list[WorkflowPlanStep], updated_at: datetime
) -> list[WorkflowStepState]:
    return [
        WorkflowStepState(
            step_id=step.step_id,
            step_order=step.step_order,
            owner_agent=step.owner_agent,
            task_description=step.task_description,
            status=step.status,
            depends_on=step.depends_on,
            updated_at=updated_at,
        )
        for step in plan
    ]


def build_planned_timestamps(
    now: datetime,
    requires_user_approval: bool,
    delegation_result: dict[str, Any] | None = None,
) -> WorkflowTimestamps:
    return WorkflowTimestamps(
        received_at=now,
        updated_at=now,
        planned_at=now,
        delegated_at=delegation_result["delegated_at"] if delegation_result else None,
        waiting_for_results_at=(
            delegation_result["waiting_for_results_at"] if delegation_result else None
        ),
        waiting_for_approval_at=(
            now
            if requires_user_approval
            else delegation_result["waiting_for_approval_at"]
            if delegation_result and "waiting_for_approval_at" in delegation_result
            else None
        ),
        completed_at=delegation_result["completed_at"] if delegation_result else None,
        blocked_at=delegation_result["blocked_at"] if delegation_result else None,
    )


def build_decision_record(
    decision_id: str,
    decision_type: WorkflowDecisionType,
    summary: str,
    actor: str,
    previous_status: WorkflowLifecycleStatus | None,
    new_status: WorkflowLifecycleStatus,
    created_at: datetime,
    related_step_id: str | None = None,
) -> WorkflowDecisionRecord:
    return WorkflowDecisionRecord(
        decision_id=decision_id,
        decision_type=decision_type,
        summary=summary,
        actor=actor,
        related_step_id=related_step_id,
        previous_status=previous_status,
        new_status=new_status,
        created_at=created_at,
    )


def find_first_step_id_by_status(
    plan: list[WorkflowPlanStep], target_status: WorkflowStepStatus
) -> str | None:
    for step in plan:
        if step.status == target_status:
            return step.step_id
    return None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_clarification_message(task_request: TaskRequest) -> str:
    clarification_lines = [
        "Request requires clarification before planning.",
        "",
        "Missing or incomplete fields:",
    ]
    for item in task_request.clarification_items:
        clarification_lines.append(f"- {item.field_name}: {item.reason}")
    return "\n".join(clarification_lines)
