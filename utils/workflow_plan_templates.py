from __future__ import annotations

from typing import Any

from contracts.task_request import TaskRequest


def build_specialist_result_format(focus: str) -> dict[str, Any]:
    return {
        "focus": focus,
        "summary": "string",
        "findings": ["string"],
        "proposed_actions": [
            {
                "action_id": "string",
                "action_type": "string",
                "details": {},
            }
        ],
        "risks": ["string"],
        "artifacts": ["string"],
    }


def build_deployment_analysis_instruction(task_request: TaskRequest) -> str:
    return build_specialist_instruction(
        task_request=task_request,
        analysis_focus=(
            "Review deployment prerequisites, rollout sequencing, release inputs, "
            "and service availability considerations."
        ),
    )


def build_infrastructure_analysis_instruction(task_request: TaskRequest) -> str:
    return build_specialist_instruction(
        task_request=task_request,
        analysis_focus=(
            "Review infrastructure dependencies, environment configuration impact, "
            "and platform prerequisites relevant to the request."
        ),
    )


def build_ci_cd_analysis_instruction(task_request: TaskRequest) -> str:
    return build_specialist_instruction(
        task_request=task_request,
        analysis_focus=(
            "Review pipeline impact, required builds or tests, artifact readiness, "
            "and release-flow constraints."
        ),
    )


def build_specialist_instruction(
    task_request: TaskRequest, analysis_focus: str
) -> str:
    work_item = task_request.standardized_work_item
    environment = (
        work_item.target_environment.value if work_item.target_environment else "unknown"
    )
    operation = work_item.operation_type.value if work_item.operation_type else "unknown"
    return (
        f"{analysis_focus} "
        f"Request: {task_request.user_request}. "
        f"Service: {work_item.service_name}. "
        f"Environment: {environment}. "
        f"Operation: {operation}. "
        "Return only JSON using the declared step format."
    )


def build_risk_policy_instruction(task_request: TaskRequest) -> str:
    return (
        "Review the structured policy input containing actions, environment, "
        "operation_type, and business_context for policy compliance, execution risk, "
        f"and approval requirements. Request: {task_request.user_request}. "
        "Return one JSON decision per proposed action."
    )


def build_human_approval_instruction(task_request: TaskRequest) -> str:
    return (
        "Present only the approval-gated actions to the human reviewer, capture a "
        f"single explicit decision, and return it in JSON. Request: {task_request.user_request}."
    )


def build_execution_handoff_instruction(task_request: TaskRequest) -> str:
    return (
        "Prepare an execution handoff containing only policy-allowed actions and "
        f"the required tool context for the request: {task_request.user_request}. "
        "Do not execute any action."
    )


def build_final_report_instruction(task_request: TaskRequest) -> str:
    return (
        "Prepare the final structured report payload for Supervisor aggregation and "
        f"publication. Summarize the request: {task_request.user_request}. "
        "Include approvals, blocked actions, and artifact references."
    )
