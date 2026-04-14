import os

from deepagents import create_deep_agent

from contracts.task_request import InputStatus, TaskRequest
from contracts.task_response import TaskResponse
from contracts.workflow_approval import WorkflowApprovalDecisionRequest
from contracts.task_response import WorkflowLifecycleStatus
from settings.supervisor import (
    SPECIALIST_SUBAGENTS,
    SUPERVISOR_AGENT_NAME,
    SUPERVISOR_SYSTEM_PROMPT,
    get_openai_model,
)
from utils.supervisor import (
    parse_planned_supervisor_output,
    read_last_message_text,
    sort_plan_steps,
)
from utils.workflow_checkpointing import get_workflow_checkpoint_store
from utils.workflow_logging import get_application_logger, log_ai_request
from utils.workflow_delegation import delegate_workflow_plan
from utils.workflow_final_report import attach_final_report
from utils.workflow_plan_builder import build_workflow_plan
from utils.workflow_risk import assess_workflow_risk, build_workflow_confidence
from utils.workflow_state import (
    TERMINAL_WORKFLOW_STATUSES,
    apply_human_approval_decision,
    append_state_transition_decision,
    sync_response_with_delegation_result,
)

logger = get_application_logger("agents.supervisor")
checkpoint_store = get_workflow_checkpoint_store()


def create_supervisor_agent(model: str | None = None):
    return create_deep_agent(
        model=get_openai_model(explicit_model=model),
        system_prompt=SUPERVISOR_SYSTEM_PROMPT,
        subagents=SPECIALIST_SUBAGENTS,
        name=SUPERVISOR_AGENT_NAME,
    )


def run_supervisor_agent(
    task_request: TaskRequest,
    model: str | None = None,
    execution_mode: str = "parallel",
) -> TaskResponse:
    if task_request.input_status == InputStatus.NEEDS_CLARIFICATION:
        response = TaskResponse.from_clarification_request(task_request=task_request)
        checkpoint_store.save(
            request_id=task_request.request_id,
            task_request=task_request,
            task_response=response,
            event="clarification_requested",
        )
        return response

    persisted_workflow = checkpoint_store.load_latest(task_request.request_id)
    if persisted_workflow:
        _, persisted_response = persisted_workflow
        if persisted_response.state.lifecycle_status == WorkflowLifecycleStatus.NEEDS_CLARIFICATION:
            persisted_workflow = None
        else:
            if (
                persisted_response.state.lifecycle_status
                in TERMINAL_WORKFLOW_STATUSES
                | {WorkflowLifecycleStatus.WAITING_FOR_APPROVAL}
            ):
                return persisted_response
            return continue_supervisor_workflow(
                task_request=task_request,
                response=persisted_response,
                model=get_openai_model(explicit_model=model),
                execution_mode=execution_mode,
            )

    selected_model = get_openai_model(explicit_model=model)
    planned_output = run_supervisor_planning(
        task_request=task_request,
        model=selected_model,
    )
    risk_assessment = assess_workflow_risk(task_request)
    plan = sort_plan_steps(planned_output["plan"])
    response = TaskResponse.from_planned_task(
        task_request=task_request,
        model=selected_model,
        plan=plan,
        confidence=planned_output["confidence"],
        risk_flags=planned_output["risk_flags"] or risk_assessment.risk_flags,
        requires_user_approval=planned_output["requires_user_approval"],
        delegation_result=None,
    )
    attach_final_report(task_request=task_request, response=response)
    checkpoint_store.save(
        request_id=task_request.request_id,
        task_request=task_request,
        task_response=response,
        event="plan_created",
    )
    return continue_supervisor_workflow(
        task_request=task_request,
        response=response,
        model=selected_model,
        execution_mode=execution_mode,
    )


def resume_supervisor_workflow(
    request_id: str,
    approval_request: WorkflowApprovalDecisionRequest,
    model: str | None = None,
    execution_mode: str = "parallel",
) -> TaskResponse:
    persisted_workflow = checkpoint_store.load_latest(request_id)
    if not persisted_workflow:
        raise ValueError(f"Workflow checkpoint for request_id '{request_id}' was not found.")

    task_request, persisted_response = persisted_workflow
    selected_model = get_openai_model(explicit_model=model)
    response = apply_human_approval_decision(
        response=persisted_response,
        approval_request=approval_request,
    )
    attach_final_report(task_request=task_request, response=response)
    checkpoint_store.save(
        request_id=request_id,
        task_request=task_request,
        task_response=response,
        event=f"approval_{approval_request.to_status().value}",
    )

    if not has_planned_steps(response):
        return response
    return continue_supervisor_workflow(
        task_request=task_request,
        response=response,
        model=selected_model,
        execution_mode=execution_mode,
    )


def continue_supervisor_workflow(
    task_request: TaskRequest,
    response: TaskResponse,
    model: str,
    execution_mode: str,
) -> TaskResponse:
    delegation_result = delegate_workflow_plan(
        plan=response.plan,
        task_request=task_request,
        model=model,
        execution_mode=execution_mode,
        existing_step_states=response.state.plan_steps,
        existing_delegated_step_ids=response.state.resume_data.delegated_step_ids,
        checkpoint_callback=lambda snapshot: persist_workflow_progress(
            task_request=task_request,
            response=response,
            delegation_result=snapshot,
            event="step_checkpoint_saved",
        ),
    )
    persist_workflow_progress(
        task_request=task_request,
        response=response,
        delegation_result=delegation_result,
        event="workflow_state_updated",
    )
    return response


def persist_workflow_progress(
    task_request: TaskRequest,
    response: TaskResponse,
    delegation_result: dict,
    event: str,
) -> None:
    sync_response_with_delegation_result(response, delegation_result)
    append_state_transition_decision(
        response=response,
        summary=build_workflow_progress_summary(delegation_result),
        new_status=delegation_result["lifecycle_status"],
        related_step_id=delegation_result["last_completed_step_id"],
    )
    attach_final_report(task_request=task_request, response=response)
    checkpoint_store.save(
        request_id=task_request.request_id,
        task_request=task_request,
        task_response=response,
        event=event,
    )


def build_workflow_progress_summary(delegation_result: dict) -> str:
    if delegation_result["lifecycle_status"] == WorkflowLifecycleStatus.WAITING_FOR_APPROVAL:
        return "Workflow paused at approval gate and saved to checkpoint."
    if delegation_result["lifecycle_status"] == WorkflowLifecycleStatus.COMPLETED:
        return "Workflow completed and final state saved to checkpoint."
    if delegation_result["lifecycle_status"] == WorkflowLifecycleStatus.BLOCKED:
        return "Workflow reached a blocked state and saved its latest checkpoint."
    if delegation_result["last_completed_step_id"]:
        return (
            "Workflow checkpoint saved after completing "
            f"{delegation_result['last_completed_step_id']}."
        )
    return "Workflow checkpoint saved without new completed steps."


def has_planned_steps(response: TaskResponse) -> bool:
    return any(step.status.value == "planned" for step in response.state.plan_steps)


def run_supervisor_planning(task_request: TaskRequest, model: str) -> dict:
    if not os.getenv("OPENAI_API_KEY"):
        return build_fallback_planning_result(task_request)

    prompt = task_request.to_prompt()
    log_ai_request(
        logger,
        request_id=task_request.request_id,
        model=model,
        prompt=prompt,
    )
    agent = create_supervisor_agent(model=model)
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ]
        }
    )

    raw_text = read_last_message_text(result=result)
    try:
        planned_output = parse_planned_supervisor_output(raw_text=raw_text)
    except Exception:
        return build_fallback_planning_result(task_request)
    return {
        "plan": planned_output.plan,
        "confidence": planned_output.confidence,
        "risk_flags": planned_output.risk_flags,
        "requires_user_approval": planned_output.requires_user_approval,
    }


def build_fallback_planning_result(task_request: TaskRequest) -> dict:
    risk_assessment = assess_workflow_risk(task_request)
    return {
        "plan": build_workflow_plan(task_request),
        "confidence": build_workflow_confidence(task_request),
        "risk_flags": risk_assessment.risk_flags,
        "requires_user_approval": risk_assessment.requires_user_approval,
    }
