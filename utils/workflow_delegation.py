from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable

from agents.specialist_factory import build_specialist_agent
from contracts.agent_input import AgentExecutionInput
from contracts.agent_session_memory import AgentSessionMemory
from contracts.agent_output import (
    AgentExecutionOutput,
    AgentExecutionStatus,
)
from contracts.task_request import TaskRequest
from contracts.task_response import (
    SpecialistAgentName,
    WorkflowLifecycleStatus,
    WorkflowPlanStep,
    WorkflowStage,
    WorkflowStepState,
    WorkflowStepStatus,
)
from settings.supervisor import is_live_ai_enabled
from utils.agent_session_memory import build_initial_session_memory, finalize_session_memory
from utils.specialist_step_contract import build_primary_error_payload, map_agent_status_to_workflow_status
from utils.workflow_policy import (
    apply_policy_decision_states,
    build_fallback_step_response as build_policy_fallback_step_response,
    build_runtime_input_context,
)
from utils.workflow_result_aggregation import (
    build_error_details,
    build_status_reason,
    build_workflow_aggregation,
    normalize_execution_details,
)

StepRunner = Callable[
    [WorkflowPlanStep, TaskRequest, dict[str, Any], str, AgentSessionMemory],
    dict[str, Any],
]
CheckpointCallback = Callable[[dict[str, Any]], None]


def delegate_workflow_plan(
    plan: list[WorkflowPlanStep],
    task_request: TaskRequest,
    model: str,
    execution_mode: str = "parallel",
    step_runner: StepRunner | None = None,
    existing_step_states: list[WorkflowStepState] | None = None,
    existing_delegated_step_ids: list[str] | None = None,
    checkpoint_callback: CheckpointCallback | None = None,
) -> dict[str, Any]:
    sorted_plan = sorted(plan, key=lambda step: step.step_order)
    mutable_plan = [step.model_copy(deep=True) for step in sorted_plan]
    step_states = (
        [step.model_copy(deep=True) for step in existing_step_states]
        if existing_step_states
        else build_initial_step_states(mutable_plan)
    )
    state_index = {step.step_id: step for step in step_states}
    plan_index = {step.step_id: step for step in mutable_plan}
    delegated_step_ids = list(existing_delegated_step_ids or [])
    for step in mutable_plan:
        if step.step_id in state_index:
            step.status = state_index[step.step_id].status
    runner = step_runner or run_specialist_step

    while True:
        ready_steps = find_ready_steps(mutable_plan, state_index)
        if not ready_steps:
            break

        if execution_mode == "sequential":
            executed_steps = [
                execute_step(
                    step=ready_steps[0],
                    task_request=task_request,
                    model=model,
                    state_index=state_index,
                    runner=runner,
                )
            ]
        else:
            with ThreadPoolExecutor(max_workers=len(ready_steps)) as executor:
                futures = [
                    executor.submit(
                        execute_step,
                        step=step,
                        task_request=task_request,
                        model=model,
                        state_index=state_index,
                        runner=runner,
                    )
                    for step in ready_steps
                ]
                executed_steps = [future.result() for future in futures]

        for executed_step in executed_steps:
            if executed_step.step_id not in delegated_step_ids:
                delegated_step_ids.append(executed_step.step_id)
            plan_index[executed_step.step_id].status = state_index[
                executed_step.step_id
            ].status
        apply_policy_decision_states(mutable_plan, step_states)
        if checkpoint_callback:
            checkpoint_callback(
                build_delegation_result(
                    plan=mutable_plan,
                    step_states=step_states,
                    delegated_step_ids=delegated_step_ids,
                )
            )

    apply_blocked_states(mutable_plan, state_index)
    for step in mutable_plan:
        step.status = state_index[step.step_id].status

    return build_delegation_result(
        plan=mutable_plan,
        step_states=step_states,
        delegated_step_ids=delegated_step_ids,
    )


def build_initial_step_states(plan: list[WorkflowPlanStep]) -> list[WorkflowStepState]:
    now = utc_now()
    return [
        WorkflowStepState(
            step_id=step.step_id,
            step_order=step.step_order,
            owner_agent=step.owner_agent,
            task_description=step.task_description,
            status=step.status,
            depends_on=step.depends_on,
            updated_at=now,
        )
        for step in plan
    ]


def find_ready_steps(
    plan: list[WorkflowPlanStep],
    state_index: dict[str, WorkflowStepState],
) -> list[WorkflowPlanStep]:
    ready_steps: list[WorkflowPlanStep] = []
    for step in plan:
        step_state = state_index[step.step_id]
        if step_state.status != WorkflowStepStatus.PLANNED:
            continue
        if not dependencies_completed(step, state_index):
            continue
        if has_missing_required_input(step.required_input_context):
            continue
        ready_steps.append(step)
    return ready_steps


def dependencies_completed(
    step: WorkflowPlanStep, state_index: dict[str, WorkflowStepState]
) -> bool:
    return all(
        state_index[dependency_id].status == WorkflowStepStatus.COMPLETED
        for dependency_id in step.depends_on
    )


def has_missing_required_input(required_input_context: dict[str, Any]) -> bool:
    return contains_missing_value(required_input_context)


def contains_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, dict):
        return any(contains_missing_value(item) for item in value.values())
    return False


def execute_step(
    step: WorkflowPlanStep,
    task_request: TaskRequest,
    model: str,
    state_index: dict[str, WorkflowStepState],
    runner: StepRunner,
) -> WorkflowPlanStep:
    dependency_results = {
        dependency_id: state_index[dependency_id].response
        for dependency_id in step.depends_on
        if state_index[dependency_id].response is not None
    }
    dependency_step_states = [
        state_index[dependency_id]
        for dependency_id in step.depends_on
        if dependency_id in state_index
    ]
    step_with_runtime_context = step.model_copy(deep=True)
    step_with_runtime_context.required_input_context = build_runtime_input_context(
        step=step,
        task_request=task_request,
        dependency_results=dependency_results,
    )
    initial_session_memory = build_initial_session_memory(
        step=step_with_runtime_context,
        task_request=task_request,
        dependency_step_states=dependency_step_states,
    )
    step_state = state_index[step.step_id]
    step_state.status = WorkflowStepStatus.DELEGATED
    step_state.updated_at = utc_now()
    raw_response = runner(
        step_with_runtime_context,
        task_request,
        dependency_results,
        model,
        initial_session_memory,
    )
    normalized_response = normalize_step_response(raw_response, initial_session_memory)
    step_state.response = normalized_response["result"]
    step_state.logs = normalized_response["logs"]
    step_state.analysis_details = normalized_response["analysis_details"]
    step_state.recommended_actions = normalized_response["recommended_actions"]
    step_state.artifacts = normalized_response["artifacts"]
    step_state.warnings = normalized_response["warnings"]
    step_state.technical_errors = normalized_response["technical_errors"]
    step_state.supervisor_data = normalized_response["supervisor_data"]
    step_state.execution_details = normalized_response["execution_details"]
    step_state.session_memory = normalized_response["session_memory"]
    step_state.error_details = normalized_response["error_details"]
    step_state.status = normalized_response["status"]
    step_state.updated_at = utc_now()
    if step_state.status != WorkflowStepStatus.COMPLETED:
        step_state.status_reason = normalized_response["status_reason"]
    return step


def normalize_step_response(
    raw_response: dict[str, Any],
    initial_session_memory: AgentSessionMemory,
) -> dict[str, Any]:
    try:
        agent_output = AgentExecutionOutput.model_validate(raw_response)
    except Exception:
        agent_output = AgentExecutionOutput(
            result={},
            logs=[],
            status=AgentExecutionStatus.FAILED,
            technical_errors=[
                {
                    "message": "Specialist agent returned an invalid response payload.",
                    "code": "invalid_agent_output",
                    "details": {"raw_response_type": type(raw_response).__name__},
                }
            ],
        )

    normalized_status = map_agent_status_to_workflow_status(agent_output.status)
    error_details = build_error_details(
        build_primary_error_payload(agent_output),
        normalized_status,
    )
    return {
        "result": agent_output.result,
        "logs": agent_output.logs,
        "analysis_details": agent_output.analysis_details,
        "recommended_actions": [
            action.model_dump(mode="json") for action in agent_output.recommended_actions
        ],
        "artifacts": agent_output.artifacts,
        "warnings": agent_output.warnings,
        "technical_errors": agent_output.technical_errors,
        "supervisor_data": agent_output.supervisor_data,
        "execution_details": normalize_execution_details(raw_response or {}),
        "session_memory": agent_output.session_memory
        or finalize_session_memory(initial_session_memory, raw_response or {}),
        "error_details": error_details,
        "status": normalized_status,
        "status_reason": build_status_reason(normalized_status, error_details),
    }


def apply_blocked_states(
    plan: list[WorkflowPlanStep],
    state_index: dict[str, WorkflowStepState],
) -> None:
    for step in plan:
        step_state = state_index[step.step_id]
        if step_state.status != WorkflowStepStatus.PLANNED:
            continue

        if has_missing_required_input(step.required_input_context):
            step_state.status = WorkflowStepStatus.BLOCKED
            step_state.status_reason = "Missing required input context."
            step_state.updated_at = utc_now()
            continue

        dependency_states = [state_index[dependency_id] for dependency_id in step.depends_on]
        if any(
            dependency_state.status
            in {
                WorkflowStepStatus.FAILED,
                WorkflowStepStatus.BLOCKED,
                WorkflowStepStatus.WAITING_FOR_APPROVAL,
            }
            for dependency_state in dependency_states
        ):
            step_state.status = WorkflowStepStatus.BLOCKED
            step_state.status_reason = "Required dependency did not reach completed status."
            step_state.updated_at = utc_now()


def determine_workflow_progress(
    step_states: list[WorkflowStepState],
) -> tuple[WorkflowLifecycleStatus, WorkflowStage]:
    if any(step.status == WorkflowStepStatus.FAILED for step in step_states):
        return WorkflowLifecycleStatus.FAILED, WorkflowStage.SPECIALIST_ANALYSIS
    if any(step.status == WorkflowStepStatus.WAITING_FOR_APPROVAL for step in step_states):
        return WorkflowLifecycleStatus.WAITING_FOR_APPROVAL, WorkflowStage.HUMAN_REVIEW
    if any(step.status == WorkflowStepStatus.BLOCKED for step in step_states):
        if all(
            step.status in {WorkflowStepStatus.COMPLETED, WorkflowStepStatus.BLOCKED}
            for step in step_states
        ):
            return WorkflowLifecycleStatus.BLOCKED, WorkflowStage.HUMAN_REVIEW
        return WorkflowLifecycleStatus.WAITING_FOR_RESULTS, WorkflowStage.SPECIALIST_ANALYSIS
    if all(step.status == WorkflowStepStatus.COMPLETED for step in step_states):
        return WorkflowLifecycleStatus.COMPLETED, WorkflowStage.COMPLETED
    if any(step.status == WorkflowStepStatus.DELEGATED for step in step_states):
        return WorkflowLifecycleStatus.DELEGATED, WorkflowStage.DELEGATION
    return WorkflowLifecycleStatus.WAITING_FOR_RESULTS, WorkflowStage.SPECIALIST_ANALYSIS


def find_next_step_id(step_states: list[WorkflowStepState]) -> str | None:
    for step in sorted(step_states, key=lambda item: item.step_order):
        if step.status == WorkflowStepStatus.PLANNED:
            return step.step_id
    return None


def build_delegation_result(
    plan: list[WorkflowPlanStep],
    step_states: list[WorkflowStepState],
    delegated_step_ids: list[str],
) -> dict[str, Any]:
    lifecycle_status, current_stage = determine_workflow_progress(step_states)
    waiting_step_ids = [
        step.step_id
        for step in step_states
        if step.status in {WorkflowStepStatus.WAITING_FOR_APPROVAL, WorkflowStepStatus.BLOCKED}
    ]
    completed_steps = [
        step for step in step_states if step.status == WorkflowStepStatus.COMPLETED
    ]
    return {
        "plan": [step.model_copy(deep=True) for step in plan],
        "step_states": [step.model_copy(deep=True) for step in step_states],
        "aggregation": build_workflow_aggregation(step_states),
        "current_stage": current_stage,
        "lifecycle_status": lifecycle_status,
        "delegated_step_ids": list(delegated_step_ids),
        "waiting_step_ids": waiting_step_ids,
        "last_completed_step_id": completed_steps[-1].step_id if completed_steps else None,
        "next_step_id": find_next_step_id(step_states),
        "completed_at": utc_now() if lifecycle_status == WorkflowLifecycleStatus.COMPLETED else None,
        "delegated_at": utc_now() if delegated_step_ids else None,
        "waiting_for_results_at": build_waiting_for_results_timestamp(step_states),
        "waiting_for_approval_at": utc_now()
        if lifecycle_status == WorkflowLifecycleStatus.WAITING_FOR_APPROVAL
        else None,
        "blocked_at": utc_now()
        if any(step.status == WorkflowStepStatus.BLOCKED for step in step_states)
        else None,
    }


def build_waiting_for_results_timestamp(
    step_states: list[WorkflowStepState],
) -> datetime | None:
    if any(step.status == WorkflowStepStatus.PLANNED for step in step_states):
        return utc_now()
    return None


def run_specialist_step(
    step: WorkflowPlanStep,
    task_request: TaskRequest,
    dependency_results: dict[str, Any],
    model: str,
    session_memory: AgentSessionMemory,
) -> dict[str, Any]:
    if not is_live_ai_enabled():
        return build_fallback_step_response(step, task_request, dependency_results)

    agent_input = build_agent_execution_input(
        step=step,
        task_request=task_request,
        dependency_results=dependency_results,
        session_memory=session_memory,
    )
    specialist_agent = build_specialist_agent(
        owner_agent=step.owner_agent,
        model=model,
        tools=build_specialist_tools(step),
    )
    return specialist_agent.run(agent_input).model_dump(mode="json")


def build_agent_execution_input(
    step: WorkflowPlanStep,
    task_request: TaskRequest,
    dependency_results: dict[str, Any],
    session_memory: AgentSessionMemory,
) -> AgentExecutionInput:
    return AgentExecutionInput.from_workflow_step(
        step_id=step.step_id,
        owner_agent=step.owner_agent.value,
        task_type=step.task_type,
        instruction=step.agent_instruction,
        target_environment=task_request.standardized_work_item.target_environment,
        technical_params=step.required_input_context,
        execution_constraints=task_request.standardized_work_item.constraints
        + step.start_conditions,
        previous_step_outputs=dependency_results,
        session_memory=session_memory,
        safety_flags=step.risk_flags
        + (["requires_user_approval"] if step.requires_user_approval else []),
        depends_on=step.depends_on,
        expected_output_json_format=step.expected_output_json_format,
        expected_result=step.expected_result,
        result_handoff_condition=step.result_handoff_condition,
        task_request=task_request,
    )


def build_fallback_step_response(
    step: WorkflowPlanStep,
    task_request: TaskRequest,
    dependency_results: dict[str, Any],
) -> dict[str, Any]:
    return build_policy_fallback_step_response(
        step=step,
        task_request=task_request,
        dependency_results=dependency_results,
    )


def build_specialist_tools(step: WorkflowPlanStep) -> list[Any]:
    return []


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
