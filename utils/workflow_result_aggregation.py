from typing import Any

from contracts.task_response import WorkflowStepState, WorkflowStepStatus
from contracts.workflow_aggregation import (
    AggregatedExecutionStatus,
    AggregatedStepResult,
    StepErrorDetails,
    WorkflowAggregationSummary,
)


def build_error_details(
    error_payload: Any, normalized_status: WorkflowStepStatus
) -> dict[str, Any] | None:
    if normalized_status != WorkflowStepStatus.FAILED:
        return None
    if isinstance(error_payload, dict):
        return {
            "message": str(error_payload.get("message") or "Specialist agent step failed."),
            "code": error_payload.get("code"),
            "details": {
                key: value
                for key, value in error_payload.items()
                if key not in {"message", "code"}
            },
        }
    if error_payload:
        return {"message": str(error_payload), "code": None, "details": {}}
    return {"message": "Specialist agent step failed.", "code": None, "details": {}}


def normalize_execution_details(raw_response: dict[str, Any]) -> dict[str, Any]:
    execution_details = raw_response.get("execution_details") or raw_response.get("details")
    if isinstance(execution_details, dict):
        return execution_details
    return {}


def build_status_reason(
    normalized_status: WorkflowStepStatus,
    error_details: dict[str, Any] | None,
) -> str | None:
    if normalized_status == WorkflowStepStatus.COMPLETED:
        return None
    if error_details:
        return error_details["message"]
    return "Specialist agent returned a non-completed status."


def build_workflow_aggregation(
    step_states: list[WorkflowStepState],
) -> WorkflowAggregationSummary:
    successful_step_ids = [
        step.step_id for step in step_states if step.status == WorkflowStepStatus.COMPLETED
    ]
    failed_step_ids = [
        step.step_id for step in step_states if step.status == WorkflowStepStatus.FAILED
    ]
    blocked_step_ids = [
        step.step_id for step in step_states if step.status == WorkflowStepStatus.BLOCKED
    ]
    waiting_step_ids = [
        step.step_id
        for step in step_states
        if step.status == WorkflowStepStatus.WAITING_FOR_APPROVAL
    ]
    problematic_step_ids = failed_step_ids + blocked_step_ids + waiting_step_ids
    return WorkflowAggregationSummary(
        step_results=[build_aggregated_step_result(step) for step in step_states],
        successful_step_ids=successful_step_ids,
        failed_step_ids=failed_step_ids,
        blocked_step_ids=blocked_step_ids,
        waiting_step_ids=waiting_step_ids,
        problematic_step_ids=problematic_step_ids,
        has_partial_result=bool(successful_step_ids) and bool(problematic_step_ids),
        next_decision=build_next_decision(
            problematic_step_ids=problematic_step_ids,
            failed_step_ids=failed_step_ids,
            waiting_step_ids=waiting_step_ids,
        ),
    )


def build_aggregated_step_result(step_state: WorkflowStepState) -> AggregatedStepResult:
    execution_status = AggregatedExecutionStatus.NOT_EXECUTED
    error = None
    if step_state.status == WorkflowStepStatus.COMPLETED:
        execution_status = AggregatedExecutionStatus.SUCCESS
    elif step_state.status == WorkflowStepStatus.FAILED:
        execution_status = AggregatedExecutionStatus.ERROR
        if step_state.error_details:
            error = StepErrorDetails.model_validate(step_state.error_details)
    return AggregatedStepResult(
        step_id=step_state.step_id,
        owner_agent=step_state.owner_agent.value,
        step_status=step_state.status.value,
        execution_status=execution_status,
        result=step_state.response,
        logs=step_state.logs,
        execution_details=step_state.execution_details,
        error=error,
        is_problematic=step_state.status
        in {
            WorkflowStepStatus.FAILED,
            WorkflowStepStatus.BLOCKED,
            WorkflowStepStatus.WAITING_FOR_APPROVAL,
        },
    )


def build_next_decision(
    problematic_step_ids: list[str],
    failed_step_ids: list[str],
    waiting_step_ids: list[str],
) -> str | None:
    if waiting_step_ids:
        return "await_user_approval"
    if failed_step_ids:
        return "review_failed_steps"
    if problematic_step_ids:
        return "review_blocked_steps"
    return None
