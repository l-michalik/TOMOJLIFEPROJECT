from __future__ import annotations

from typing import Any

from contracts.final_report import (
    FinalReportAgentResult,
    FinalReportStepSummary,
    WorkflowFinalReport,
)
from contracts.task_request import TaskRequest
from contracts.task_response import (
    SpecialistAgentName,
    TaskResponse,
    WorkflowStepState,
    WorkflowStepStatus,
)
from utils.workflow_policy import (
    collect_policy_decisions,
    extract_approval_required_actions,
    extract_blocked_actions,
)


def attach_final_report(
    task_request: TaskRequest,
    response: TaskResponse,
) -> TaskResponse:
    report = build_workflow_final_report(task_request=task_request, response=response)
    response.final_report = report
    response.answer = report.publication_message
    return response


def build_workflow_final_report(
    task_request: TaskRequest,
    response: TaskResponse,
) -> WorkflowFinalReport:
    plan = response.plan
    plan_steps = response.state.plan_steps if response.state else []
    policy_decisions = collect_policy_decisions(build_policy_dependency_results(plan_steps))
    blocked_actions = extract_blocked_actions(policy_decisions)
    approval_required_actions = extract_approval_required_actions(policy_decisions)
    artifact_references = collect_artifact_references(plan_steps)

    report = WorkflowFinalReport(
        request_id=response.request_id,
        source=task_request.source.value,
        final_status=response.state.lifecycle_status.value if response.state else response.status.value,
        task_goal_summary=build_task_goal_summary(task_request),
        planned_steps=[build_step_summary(step) for step in plan],
        executed_steps=[
            build_step_summary(step)
            for step in plan_steps
            if step.status
            in {
                WorkflowStepStatus.COMPLETED,
                WorkflowStepStatus.FAILED,
                WorkflowStepStatus.BLOCKED,
                WorkflowStepStatus.WAITING_FOR_APPROVAL,
            }
        ],
        specialist_results=build_specialist_results(plan_steps),
        errors=collect_error_messages(plan_steps),
        policy_blocked_actions=blocked_actions,
        approval_required_actions=approval_required_actions,
        user_decisions_required=build_user_decisions_required(response, approval_required_actions),
        log_references=build_log_references(response, plan_steps),
        artifact_references=artifact_references,
        metadata=build_report_metadata(task_request=task_request, response=response),
        publication_message="",
    )
    report.publication_message = render_publication_message(report)
    return report


def build_task_goal_summary(task_request: TaskRequest) -> str:
    environment = task_request.standardized_work_item.target_environment
    service_name = task_request.standardized_work_item.service_name
    summary_parts = [task_request.user_request.strip()]
    if environment is not None:
        summary_parts.append(f"Environment: {environment.value}.")
    if service_name:
        summary_parts.append(f"Service: {service_name}.")
    return " ".join(summary_parts)


def build_step_summary(step: Any) -> FinalReportStepSummary:
    return FinalReportStepSummary(
        step_id=step.step_id,
        owner_agent=step.owner_agent.value,
        task_description=step.task_description,
        status=step.status.value if hasattr(step.status, "value") else str(step.status),
    )


def build_specialist_results(
    step_states: list[WorkflowStepState],
) -> list[FinalReportAgentResult]:
    return [
        FinalReportAgentResult(
            agent_name=step.owner_agent.value,
            step_id=step.step_id,
            status=step.status.value,
            summary=extract_step_summary(step),
            artifacts=collect_step_artifacts(step.response),
            logs=step.logs,
            error=step.error_details["message"] if step.error_details else None,
        )
        for step in step_states
    ]


def extract_step_summary(step: WorkflowStepState) -> str:
    if step.error_details:
        return step.error_details["message"]
    if not isinstance(step.response, dict):
        return step.task_description
    if "summary" in step.response:
        return str(step.response["summary"])
    if "final_report" in step.response and isinstance(step.response["final_report"], dict):
        final_report = step.response["final_report"]
        if "summary" in final_report:
            return str(final_report["summary"])
    if "approval_decision" in step.response:
        decision = step.response["approval_decision"]
        if isinstance(decision, dict):
            return f"Approval decision: {decision.get('status', 'unknown')}."
    if "decisions" in step.response:
        return "Risk/Policy review completed."
    if "execution_handoff" in step.response:
        return "Execution handoff prepared."
    return step.task_description


def collect_error_messages(step_states: list[WorkflowStepState]) -> list[str]:
    errors: list[str] = []
    for step in step_states:
        if step.error_details:
            errors.append(f"{step.step_id}: {step.error_details['message']}")
        elif step.status == WorkflowStepStatus.BLOCKED and step.status_reason:
            errors.append(f"{step.step_id}: {step.status_reason}")
    return errors


def build_user_decisions_required(
    response: TaskResponse,
    approval_required_actions: list[str],
) -> list[str]:
    if not response.state:
        return []
    if response.state.lifecycle_status.value != "waiting_for_approval":
        return []
    if approval_required_actions:
        return [f"Approve or reject actions: {', '.join(approval_required_actions)}."]
    return ["Workflow is waiting for a user approval decision."]


def build_log_references(
    response: TaskResponse,
    step_states: list[WorkflowStepState],
) -> list[str]:
    references = []
    if response.state:
        references.append(f"workflow_id={response.state.workflow_id}")
        references.append(f"checkpoint_id={response.state.resume_data.checkpoint_id}")
    references.extend(
        f"{step.step_id}: {len(step.logs)} log entries"
        for step in step_states
        if step.logs
    )
    return references


def collect_artifact_references(step_states: list[WorkflowStepState]) -> list[str]:
    artifact_references: list[str] = []
    for step in step_states:
        artifact_references.extend(collect_step_artifacts(step.response))
    return deduplicate_preserving_order(artifact_references)


def collect_step_artifacts(response_payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(response_payload, dict):
        return []
    artifact_values = response_payload.get("artifacts")
    if not isinstance(artifact_values, list) and "final_report" in response_payload:
        final_report = response_payload["final_report"]
        if isinstance(final_report, dict):
            artifact_values = final_report.get("artifacts")
    if not isinstance(artifact_values, list):
        return []
    return [str(item) for item in artifact_values]


def build_report_metadata(
    task_request: TaskRequest,
    response: TaskResponse,
) -> dict[str, Any]:
    metadata = {
        "user_id": task_request.user_id,
        "priority": task_request.params.priority.value if task_request.params.priority else None,
        "ticket_id": task_request.params.ticket_id,
        "conversation_id": task_request.params.conversation_id,
        "confidence": response.confidence,
        "risk_flags": response.risk_flags,
    }
    if response.state:
        metadata["current_stage"] = response.state.current_stage.value
        metadata["next_step_id"] = response.state.resume_data.next_step_id
    return metadata


def build_policy_dependency_results(
    step_states: list[WorkflowStepState],
) -> dict[str, Any]:
    return {
        step.step_id: step.response
        for step in step_states
        if step.owner_agent == SpecialistAgentName.RISK_POLICY_AGENT and step.response is not None
    }


def deduplicate_preserving_order(values: list[str]) -> list[str]:
    unique_values: list[str] = []
    seen_values: set[str] = set()
    for value in values:
        if value in seen_values:
            continue
        seen_values.add(value)
        unique_values.append(value)
    return unique_values


def render_publication_message(report: WorkflowFinalReport) -> str:
    lines = [
        f"Task report for `{report.request_id}`",
        "",
        f"- Goal: {report.task_goal_summary}",
        f"- Final status: {report.final_status}",
    ]
    if report.metadata.get("ticket_id"):
        lines.append(f"- Ticket: {report.metadata['ticket_id']}")
    if report.metadata.get("current_stage"):
        lines.append(f"- Current stage: {report.metadata['current_stage']}")

    lines.extend(render_section("Planned steps", render_step_lines(report.planned_steps)))
    lines.extend(render_section("Executed steps", render_step_lines(report.executed_steps)))
    lines.extend(
        render_section(
            "Subagent results",
            [
                (
                    f"- {result.agent_name} [{result.step_id}] {result.status}: "
                    f"{result.summary}"
                )
                for result in report.specialist_results
            ],
        )
    )
    lines.extend(render_section("Errors", [f"- {error}" for error in report.errors]))
    lines.extend(
        render_section(
            "Policy-blocked actions",
            [f"- {action_id}" for action_id in report.policy_blocked_actions],
        )
    )
    lines.extend(
        render_section(
            "Approval-required actions",
            [f"- {action_id}" for action_id in report.approval_required_actions],
        )
    )
    lines.extend(
        render_section(
            "User decisions required",
            [f"- {item}" for item in report.user_decisions_required],
        )
    )
    lines.extend(
        render_section("Log references", [f"- {reference}" for reference in report.log_references])
    )
    lines.extend(
        render_section(
            "Artifact references",
            [f"- {reference}" for reference in report.artifact_references],
        )
    )
    return "\n".join(lines)


def render_section(title: str, items: list[str]) -> list[str]:
    if not items:
        return [f"{title}: none", ""]
    return [f"{title}:"] + items + [""]


def render_step_lines(steps: list[FinalReportStepSummary]) -> list[str]:
    return [
        f"- {step.step_id} {step.owner_agent} {step.status}: {step.task_description}"
        for step in steps
    ]
