from __future__ import annotations

from typing import Any

from contracts.agent_output import AgentExecutionOutput, AgentExecutionStatus
from contracts.task_response import SpecialistAgentName, WorkflowStepStatus


def build_step_system_prompt(owner_agent: SpecialistAgentName) -> str:
    return (
        f"You are {owner_agent.value}. "
        "Return only valid JSON using the standardized agent output contract. "
        "Allowed statuses are completed, failed, blocked, and waiting_for_approval."
    )


def build_step_request_log_summary(owner_agent: SpecialistAgentName) -> str:
    summaries = {
        SpecialistAgentName.DEPLOYMENT_AGENT: "Analyze the deployment plan and release actions.",
        SpecialistAgentName.INFRA_AGENT: "Analyze infrastructure dependencies and required changes.",
        SpecialistAgentName.CI_CD_AGENT: "Analyze the CI/CD pipeline and release flow requirements.",
        SpecialistAgentName.RISK_POLICY_AGENT: "Review proposed actions for policy and approval requirements.",
        SpecialistAgentName.EXECUTION_AGENT: "Prepare the execution handoff for approved actions.",
        SpecialistAgentName.HUMAN_REVIEW_INTERFACE: "Prepare the human approval checkpoint details.",
    }
    return summaries.get(owner_agent, "Execute the assigned workflow step.")


def build_step_response_log_summary(owner_agent: SpecialistAgentName) -> str:
    summaries = {
        SpecialistAgentName.DEPLOYMENT_AGENT: "Deployment analysis result received.",
        SpecialistAgentName.INFRA_AGENT: "Infrastructure analysis result received.",
        SpecialistAgentName.CI_CD_AGENT: "CI/CD analysis result received.",
        SpecialistAgentName.RISK_POLICY_AGENT: "Risk and policy review result received.",
        SpecialistAgentName.EXECUTION_AGENT: "Execution handoff result received.",
        SpecialistAgentName.HUMAN_REVIEW_INTERFACE: "Human review checkpoint result received.",
    }
    return summaries.get(owner_agent, "Agent returned the workflow step result.")


def build_step_agent_name(owner_agent: SpecialistAgentName) -> str:
    return owner_agent.value.lower().replace("/", " ").replace(" ", "-")


def map_agent_status_to_workflow_status(
    status: AgentExecutionStatus,
) -> WorkflowStepStatus:
    mapping = {
        AgentExecutionStatus.COMPLETED: WorkflowStepStatus.COMPLETED,
        AgentExecutionStatus.FAILED: WorkflowStepStatus.FAILED,
        AgentExecutionStatus.BLOCKED: WorkflowStepStatus.BLOCKED,
        AgentExecutionStatus.WAITING_FOR_APPROVAL: WorkflowStepStatus.WAITING_FOR_APPROVAL,
    }
    return mapping[status]


def build_primary_error_payload(
    agent_output: AgentExecutionOutput,
) -> dict[str, Any] | None:
    if not agent_output.technical_errors:
        return None
    primary_error = agent_output.technical_errors[0]
    return primary_error.model_dump(mode="json")
