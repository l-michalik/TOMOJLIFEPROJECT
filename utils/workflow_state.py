from __future__ import annotations

from typing import Any

from contracts.workflow_approval import WorkflowApprovalDecisionRequest
from contracts.task_response import (
    SpecialistAgentName,
    TaskResponse,
    WorkflowDecisionType,
    WorkflowLifecycleStatus,
    WorkflowPlanStep,
    WorkflowStage,
    WorkflowStepState,
    WorkflowStepStatus,
    build_decision_record,
    utc_now,
)
from utils.workflow_policy import (
    collect_policy_decisions,
    extract_approval_required_actions,
    extract_approved_actions,
)
from utils.workflow_result_aggregation import build_workflow_aggregation

TERMINAL_WORKFLOW_STATUSES = {
    WorkflowLifecycleStatus.COMPLETED,
    WorkflowLifecycleStatus.FAILED,
    WorkflowLifecycleStatus.BLOCKED,
}


def sync_response_with_delegation_result(
    response: TaskResponse,
    delegation_result: dict[str, Any],
) -> TaskResponse:
    response.plan = delegation_result["plan"]
    response.state.plan_steps = delegation_result["step_states"]
    response.state.aggregation = delegation_result["aggregation"]
    response.state.current_stage = delegation_result["current_stage"]
    response.state.lifecycle_status = delegation_result["lifecycle_status"]
    response.state.resume_data.last_completed_step_id = delegation_result["last_completed_step_id"]
    response.state.resume_data.next_step_id = delegation_result["next_step_id"]
    response.state.resume_data.delegated_step_ids = delegation_result["delegated_step_ids"]
    response.state.resume_data.waiting_step_ids = delegation_result["waiting_step_ids"]
    response.state.timestamps.delegated_at = delegation_result["delegated_at"]
    response.state.timestamps.waiting_for_results_at = delegation_result[
        "waiting_for_results_at"
    ]
    response.state.timestamps.waiting_for_approval_at = delegation_result[
        "waiting_for_approval_at"
    ]
    response.state.timestamps.completed_at = delegation_result["completed_at"]
    response.state.timestamps.blocked_at = delegation_result["blocked_at"]
    response.requires_user_approval = (
        response.state.lifecycle_status == WorkflowLifecycleStatus.WAITING_FOR_APPROVAL
    )
    return response


def append_state_transition_decision(
    response: TaskResponse,
    summary: str,
    new_status: WorkflowLifecycleStatus,
    related_step_id: str | None = None,
) -> None:
    previous_status = response.state.decision_history[-1].new_status
    response.state.decision_history.append(
        build_decision_record(
            decision_id=f"DEC-{len(response.state.decision_history) + 1}",
            decision_type=WorkflowDecisionType.STATE_TRANSITION,
            summary=summary,
            actor="Supervisor",
            previous_status=previous_status,
            new_status=new_status,
            created_at=utc_now(),
            related_step_id=related_step_id,
        )
    )


def apply_human_approval_decision(
    response: TaskResponse,
    approval_request: WorkflowApprovalDecisionRequest,
) -> TaskResponse:
    plan_index = {step.step_id: step for step in response.plan}
    state_index = {step.step_id: step for step in response.state.plan_steps}
    approval_steps = [
        step
        for step in response.state.plan_steps
        if step.owner_agent == SpecialistAgentName.HUMAN_REVIEW_INTERFACE
        and "approval_decision" in plan_index[step.step_id].expected_output_json_format
        and step.status == WorkflowStepStatus.WAITING_FOR_APPROVAL
    ]
    if not approval_steps:
        raise ValueError("Workflow is not waiting for human approval.")

    approval_step = approval_steps[0]
    policy_step = find_policy_dependency_step(approval_step, state_index)
    policy_decisions = collect_policy_decisions(
        {"policy": policy_step.response if policy_step else None}
    )
    approval_required_actions = extract_approval_required_actions(policy_decisions)
    approval_status = approval_request.to_status()
    approval_decisions = build_post_approval_policy_decisions(
        policy_decisions=policy_decisions,
        approved=approval_request.approved,
    )

    approval_step.status = WorkflowStepStatus.COMPLETED
    approval_step.status_reason = None
    approval_step.response = {
        "approval_decision": {
            "status": approval_status.value,
            "decision_by": approval_request.decision_by,
            "decision_reason": approval_request.decision_reason or "",
        },
        "approval_required_actions": approval_required_actions,
        "decisions": approval_decisions,
    }
    approval_step.logs.append(
        f"Human approval decision recorded: {approval_status.value} by {approval_request.decision_by}."
    )
    approval_step.updated_at = utc_now()
    plan_index[approval_step.step_id].status = WorkflowStepStatus.COMPLETED

    execution_steps = find_execution_steps_depending_on(approval_step.step_id, response.plan)
    report_steps = find_non_execution_steps_depending_on(approval_step.step_id, response.plan)
    if approval_request.approved:
        approved_actions = extract_approved_actions(approval_decisions)
        for execution_step in execution_steps:
            state_step = state_index[execution_step.step_id]
            if approved_actions:
                state_step.status = WorkflowStepStatus.PLANNED
                state_step.status_reason = None
            else:
                state_step.status = WorkflowStepStatus.BLOCKED
                state_step.status_reason = (
                    "Risk/Policy Agent did not allow any action for execution."
                )
            state_step.updated_at = utc_now()
            execution_step.status = state_step.status
        for report_step in report_steps:
            report_state = state_index[report_step.step_id]
            report_state.status = WorkflowStepStatus.PLANNED
            report_state.status_reason = None
            report_state.updated_at = utc_now()
            report_step.status = WorkflowStepStatus.PLANNED
        response.state.lifecycle_status = WorkflowLifecycleStatus.PLANNED
        response.state.current_stage = WorkflowStage.EXECUTION
        response.requires_user_approval = False
        response.state.timestamps.waiting_for_approval_at = None
        response.state.resume_data.waiting_step_ids = []
        response.state.resume_data.next_step_id = approval_step.step_id
        append_state_transition_decision(
            response=response,
            summary="Human approval granted. Workflow resumed from the last checkpoint.",
            new_status=WorkflowLifecycleStatus.PLANNED,
            related_step_id=approval_step.step_id,
        )
    else:
        for execution_step in execution_steps:
            state_step = state_index[execution_step.step_id]
            state_step.status = WorkflowStepStatus.BLOCKED
            state_step.status_reason = "Human reviewer rejected approval-gated actions."
            state_step.updated_at = utc_now()
            execution_step.status = WorkflowStepStatus.BLOCKED
        for report_step in report_steps:
            report_state = state_index[report_step.step_id]
            report_state.status = WorkflowStepStatus.PLANNED
            report_state.status_reason = None
            report_state.updated_at = utc_now()
            report_step.status = WorkflowStepStatus.PLANNED
        response.state.lifecycle_status = WorkflowLifecycleStatus.BLOCKED
        response.state.current_stage = WorkflowStage.HUMAN_REVIEW
        response.requires_user_approval = False
        response.state.timestamps.waiting_for_approval_at = None
        append_state_transition_decision(
            response=response,
            summary="Human approval rejected. Execution remains blocked.",
            new_status=WorkflowLifecycleStatus.BLOCKED,
            related_step_id=approval_step.step_id,
        )

    response.state.aggregation = build_workflow_aggregation(response.state.plan_steps)
    response.state.resume_data.last_completed_step_id = approval_step.step_id
    response.state.resume_data.next_step_id = find_next_step_id(response.state.plan_steps)
    response.state.resume_data.waiting_step_ids = response.state.aggregation.waiting_step_ids
    return response


def find_policy_dependency_step(
    approval_step: WorkflowStepState,
    state_index: dict[str, WorkflowStepState],
) -> WorkflowStepState | None:
    for dependency_id in approval_step.depends_on:
        dependency_step = state_index.get(dependency_id)
        if dependency_step and dependency_step.owner_agent == SpecialistAgentName.RISK_POLICY_AGENT:
            return dependency_step
    return None


def find_execution_steps_depending_on(
    approval_step_id: str,
    plan: list[WorkflowPlanStep],
) -> list[WorkflowPlanStep]:
    return [
        step
        for step in plan
        if step.owner_agent == SpecialistAgentName.EXECUTION_AGENT
        and approval_step_id in step.depends_on
    ]


def find_non_execution_steps_depending_on(
    approval_step_id: str,
    plan: list[WorkflowPlanStep],
) -> list[WorkflowPlanStep]:
    return [
        step
        for step in plan
        if step.owner_agent != SpecialistAgentName.EXECUTION_AGENT
        and approval_step_id in step.depends_on
        and "approval_decision" not in step.expected_output_json_format
    ]


def build_post_approval_policy_decisions(
    policy_decisions: list[dict[str, Any]],
    approved: bool,
) -> list[dict[str, Any]]:
    if not approved:
        return policy_decisions
    return [
        {
            **decision,
            "requires_approval": False,
        }
        for decision in policy_decisions
    ]


def find_next_step_id(step_states: list[WorkflowStepState]) -> str | None:
    for step in sorted(step_states, key=lambda item: item.step_order):
        if step.status == WorkflowStepStatus.PLANNED:
            return step.step_id
    return None
