from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from contracts.task_request import TaskRequest
from contracts.task_response import (
    SpecialistAgentName,
    WorkflowPlanStep,
    WorkflowStepState,
    WorkflowStepStatus,
)


def build_runtime_input_context(
    step: WorkflowPlanStep,
    task_request: TaskRequest,
    dependency_results: dict[str, Any],
) -> dict[str, Any]:
    runtime_input_context = deepcopy(step.required_input_context)
    if step.owner_agent == SpecialistAgentName.RISK_POLICY_AGENT:
        runtime_input_context.update(
            {
                "actions": collect_proposed_actions(task_request, dependency_results),
                "environment": enum_value_or_unknown(
                    task_request.standardized_work_item.target_environment
                ),
                "operation_type": enum_value_or_unknown(
                    task_request.standardized_work_item.operation_type
                ),
                "business_context": build_business_context(task_request),
            }
        )
    elif step.owner_agent == SpecialistAgentName.HUMAN_REVIEW_INTERFACE:
        runtime_input_context.update(
            {
                "approval_required_actions": extract_approval_required_actions(
                    collect_policy_decisions(dependency_results)
                ),
            }
        )
    elif step.owner_agent == SpecialistAgentName.EXECUTION_AGENT:
        decisions = collect_policy_decisions(dependency_results)
        runtime_input_context.update(
            {
                "approved_actions": extract_approved_actions(decisions),
                "blocked_actions": extract_blocked_actions(decisions),
                "approval_required_actions": extract_approval_required_actions(decisions),
            }
        )
    return runtime_input_context


def build_fallback_step_response(
    step: WorkflowPlanStep,
    task_request: TaskRequest,
    dependency_results: dict[str, Any],
) -> dict[str, Any]:
    if step.owner_agent == SpecialistAgentName.RISK_POLICY_AGENT:
        return build_fallback_risk_response(task_request, dependency_results)
    if step.owner_agent == SpecialistAgentName.EXECUTION_AGENT:
        return build_fallback_execution_response(dependency_results)
    if step.owner_agent == SpecialistAgentName.HUMAN_REVIEW_INTERFACE:
        return build_fallback_human_review_response(step, dependency_results)
    return build_fallback_specialist_response(step, task_request, dependency_results)


def apply_policy_decision_states(
    plan_steps: list[WorkflowPlanStep],
    step_states: list[WorkflowStepState],
) -> None:
    plan_index = {step.step_id: step for step in plan_steps}
    state_index = {step.step_id: step for step in step_states}
    for risk_step in step_states:
        if risk_step.owner_agent != SpecialistAgentName.RISK_POLICY_AGENT:
            continue
        decisions = collect_policy_decisions({"risk": risk_step.response})
        if not decisions:
            continue

        approval_required_actions = extract_approval_required_actions(decisions)
        approved_actions = extract_approved_actions(decisions)
        human_review_steps = find_dependent_steps(
            plan_index=plan_index,
            state_index=state_index,
            dependency_step_id=risk_step.step_id,
            owner_agent=SpecialistAgentName.HUMAN_REVIEW_INTERFACE,
        )
        execution_steps = find_execution_steps(state_index, risk_step.step_id, human_review_steps)

        if approval_required_actions:
            if human_review_steps:
                for human_review_step in human_review_steps:
                    if human_review_step.status == WorkflowStepStatus.PLANNED:
                        human_review_step.status = WorkflowStepStatus.WAITING_FOR_APPROVAL
                        human_review_step.status_reason = (
                            "Risk/Policy Agent requires approval before execution."
                        )
                        human_review_step.response = {
                            "approval_required_actions": approval_required_actions
                        }
                        human_review_step.updated_at = utc_now()
            elif risk_step.status == WorkflowStepStatus.COMPLETED:
                risk_step.status = WorkflowStepStatus.WAITING_FOR_APPROVAL
                risk_step.status_reason = (
                    "Risk/Policy Agent requires approval before execution."
                )
                risk_step.updated_at = utc_now()

            for execution_step in execution_steps:
                if execution_step.status in {
                    WorkflowStepStatus.PLANNED,
                    WorkflowStepStatus.BLOCKED,
                }:
                    execution_step.status = WorkflowStepStatus.BLOCKED
                    execution_step.status_reason = (
                        "Execution is blocked until approval-gated actions are resolved."
                    )
                    execution_step.updated_at = utc_now()
            continue

        for human_review_step in human_review_steps:
            if human_review_step.status in {
                WorkflowStepStatus.PLANNED,
                WorkflowStepStatus.WAITING_FOR_APPROVAL,
                WorkflowStepStatus.BLOCKED,
            }:
                human_review_step.status = WorkflowStepStatus.COMPLETED
                human_review_step.status_reason = None
                human_review_step.response = {
                    "approval_decision": {"status": "not_required"},
                    "approval_required_actions": [],
                }
                human_review_step.updated_at = utc_now()

        for execution_step in execution_steps:
            if execution_step.status not in {
                WorkflowStepStatus.PLANNED,
                WorkflowStepStatus.BLOCKED,
            }:
                continue
            if approved_actions:
                execution_step.status = WorkflowStepStatus.PLANNED
                execution_step.status_reason = None
            else:
                execution_step.status = WorkflowStepStatus.BLOCKED
                execution_step.status_reason = (
                    "Risk/Policy Agent did not allow any action for execution."
                )
            execution_step.updated_at = utc_now()


def collect_proposed_actions(
    task_request: TaskRequest, dependency_results: dict[str, Any]
) -> list[dict[str, Any]]:
    collected_actions: list[dict[str, Any]] = []
    seen_action_ids: set[str] = set()
    for dependency_step_id, dependency_result in dependency_results.items():
        if not isinstance(dependency_result, dict):
            continue
        raw_actions = dependency_result.get("proposed_actions", [])
        if not isinstance(raw_actions, list):
            continue
        for index, raw_action in enumerate(raw_actions, start=1):
            if not isinstance(raw_action, dict):
                continue
            action_id = str(raw_action.get("action_id") or f"{dependency_step_id}-ACTION-{index}")
            if action_id in seen_action_ids:
                continue
            seen_action_ids.add(action_id)
            action_details = deepcopy(raw_action.get("details") or {})
            if task_request.standardized_work_item.service_name:
                action_details.setdefault(
                    "service_name", task_request.standardized_work_item.service_name
                )
            collected_actions.append(
                {
                    "action_id": action_id,
                    "type": str(
                        raw_action.get("action_type")
                        or enum_value_or_unknown(
                            task_request.standardized_work_item.operation_type
                        )
                    ),
                    "environment": enum_value_or_unknown(
                        task_request.standardized_work_item.target_environment
                    ),
                    "details": action_details,
                    "source_step_id": dependency_step_id,
                }
            )
    if collected_actions:
        return collected_actions
    return [build_default_action(task_request, "SUPERVISOR-ACTION-1")]


def collect_policy_decisions(
    dependency_results: dict[str, Any]
) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for dependency_result in dependency_results.values():
        if not isinstance(dependency_result, dict):
            continue
        raw_decisions = dependency_result.get("decisions", [])
        if not isinstance(raw_decisions, list):
            continue
        for raw_decision in raw_decisions:
            if not isinstance(raw_decision, dict):
                continue
            decisions.append(
                {
                    "action_id": str(raw_decision.get("action_id") or "unknown-action"),
                    "allowed": bool(raw_decision.get("allowed")),
                    "requires_approval": bool(
                        raw_decision.get("requires_approval")
                        if "requires_approval" in raw_decision
                        else raw_decision.get("requiresApproval")
                    ),
                    "reason": str(raw_decision.get("reason") or ""),
                }
            )
    return decisions


def extract_approved_actions(decisions: list[dict[str, Any]]) -> list[str]:
    return [
        decision["action_id"]
        for decision in decisions
        if decision["allowed"] and not decision["requires_approval"]
    ]


def extract_blocked_actions(decisions: list[dict[str, Any]]) -> list[str]:
    return [decision["action_id"] for decision in decisions if not decision["allowed"]]


def extract_approval_required_actions(decisions: list[dict[str, Any]]) -> list[str]:
    return [
        decision["action_id"]
        for decision in decisions
        if decision["allowed"] and decision["requires_approval"]
    ]


def build_business_context(task_request: TaskRequest) -> dict[str, Any]:
    return {
        "request_id": task_request.request_id,
        "user_id": task_request.user_id,
        "source": task_request.source.value,
        "priority": enum_value_or_unknown(task_request.params.priority),
        "service_name": task_request.standardized_work_item.service_name,
        "ticket_id": task_request.params.ticket_id,
        "conversation_id": task_request.params.conversation_id,
        "user_request": task_request.user_request,
        "constraints": task_request.standardized_work_item.constraints,
    }


def build_default_action(
    task_request: TaskRequest, action_id: str
) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "action_type": enum_value_or_unknown(task_request.standardized_work_item.operation_type),
        "details": {
            "service_name": task_request.standardized_work_item.service_name,
            "execution_parameters": deepcopy(
                task_request.standardized_work_item.execution_parameters
            ),
        },
    }


def build_fallback_specialist_response(
    step: WorkflowPlanStep,
    task_request: TaskRequest,
    dependency_results: dict[str, Any],
) -> dict[str, Any]:
    action = build_default_action(task_request, f"{step.step_id}-ACTION-1")
    return {
        "result": {
            "summary": step.expected_result,
            "findings": [step.task_description],
            "proposed_actions": [action],
            "risks": step.risk_flags,
            "artifacts": [],
            "dependency_step_ids": sorted(dependency_results),
        },
        "logs": [
            f"Delegated step {step.step_id} to {step.owner_agent.value}.",
            "Fallback specialist response generated without external model invocation.",
        ],
        "execution_details": {
            "response_source": "fallback",
            "dependency_count": len(dependency_results),
        },
        "status": WorkflowStepStatus.COMPLETED.value,
    }


def build_fallback_risk_response(
    task_request: TaskRequest,
    dependency_results: dict[str, Any],
) -> dict[str, Any]:
    actions = collect_proposed_actions(task_request, dependency_results)
    decisions = []
    for action in actions:
        requires_approval = (
            action["environment"] == "prod"
            or "requires_approval" in task_request.standardized_work_item.constraints
        )
        decisions.append(
            {
                "action_id": action["action_id"],
                "allowed": True,
                "requires_approval": requires_approval,
                "reason": (
                    "Production or explicitly approval-gated action requires human review."
                    if requires_approval
                    else "Action is allowed by fallback policy evaluation."
                ),
                "applied_policies": ["fallback_policy_gate"],
            }
        )
    return {
        "result": {"decisions": decisions},
        "logs": ["Fallback Risk/Policy assessment generated from aggregated actions."],
        "execution_details": {"response_source": "fallback", "action_count": len(actions)},
        "status": WorkflowStepStatus.COMPLETED.value,
    }


def build_fallback_execution_response(
    dependency_results: dict[str, Any],
) -> dict[str, Any]:
    decisions = collect_policy_decisions(dependency_results)
    return {
        "result": {
            "execution_handoff": {
                "approved_actions": extract_approved_actions(decisions),
                "blocked_actions": extract_blocked_actions(decisions),
                "required_tools": [],
            }
        },
        "logs": ["Fallback execution handoff generated from policy decisions."],
        "execution_details": {"response_source": "fallback"},
        "status": WorkflowStepStatus.COMPLETED.value,
    }


def build_fallback_human_review_response(
    step: WorkflowPlanStep,
    dependency_results: dict[str, Any],
) -> dict[str, Any]:
    decisions = collect_policy_decisions(dependency_results)
    if "final_report" in step.expected_output_json_format:
        return {
            "result": {
                "final_report": {
                    "summary": step.expected_result,
                    "executed_actions": extract_approved_actions(decisions),
                    "blocked_actions": extract_blocked_actions(decisions),
                    "approvals": extract_approval_required_actions(decisions),
                    "artifacts": [],
                }
            },
            "logs": ["Fallback final report generated from policy decisions."],
            "execution_details": {"response_source": "fallback"},
            "status": WorkflowStepStatus.COMPLETED.value,
        }
    return {
        "result": {
            "approval_decision": {"status": "not_required"},
            "approval_required_actions": extract_approval_required_actions(decisions),
        },
        "logs": ["Fallback human review response generated."],
        "execution_details": {"response_source": "fallback"},
        "status": WorkflowStepStatus.COMPLETED.value,
    }


def find_dependent_steps(
    plan_index: dict[str, WorkflowPlanStep],
    state_index: dict[str, WorkflowStepState],
    dependency_step_id: str,
    owner_agent: SpecialistAgentName,
) -> list[WorkflowStepState]:
    return [
        step
        for step in state_index.values()
        if step.owner_agent == owner_agent and dependency_step_id in step.depends_on
        and "approval_decision"
        in plan_index[step.step_id].expected_output_json_format
    ]


def find_execution_steps(
    state_index: dict[str, WorkflowStepState],
    risk_step_id: str,
    human_review_steps: list[WorkflowStepState],
) -> list[WorkflowStepState]:
    human_review_step_ids = {step.step_id for step in human_review_steps}
    return [
        step
        for step in state_index.values()
        if step.owner_agent == SpecialistAgentName.EXECUTION_AGENT
        and (
            risk_step_id in step.depends_on
            or bool(human_review_step_ids.intersection(step.depends_on))
        )
    ]


def enum_value_or_unknown(value: Any) -> str:
    if value is None:
        return "unknown"
    return str(value.value)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
