from __future__ import annotations

from typing import Any

from contracts.agent_input import AgentTaskType
from contracts.task_request import OperationType, TaskRequest
from contracts.task_response import (
    SpecialistAgentName,
    WorkflowPlanStep,
    WorkflowStepStatus,
)
from contracts.workflow_routing import SpecialistDomain, TaskRoutingDecision
from utils.workflow_plan_templates import (
    build_ci_cd_analysis_instruction,
    build_deployment_analysis_instruction,
    build_infrastructure_analysis_instruction,
    build_specialist_result_format,
)


def build_task_specific_step(
    *,
    task_request: TaskRequest,
    routing_decision: TaskRoutingDecision,
    base_context: dict[str, Any],
    plan_risk_flags: list[str],
    step_order: int,
    depends_on: list[str],
) -> WorkflowPlanStep:
    operation_type = task_request.standardized_work_item.operation_type
    if routing_decision.requires_human_resolution:
        return build_plan_step(
            step_order=step_order,
            owner_agent=SpecialistAgentName.HUMAN_REVIEW_INTERFACE,
            task_type=AgentTaskType.HUMAN_APPROVAL,
            task_description="Resolve ambiguous specialist routing before workflow delegation.",
            agent_instruction=(
                "Review the routing ambiguity, decide which specialist domain owns "
                "the workflow, and return JSON only."
            ),
            expected_output_json_format={
                "routing_resolution": {
                    "selected_domain": "deployment|infrastructure|ci_cd",
                    "reason": "string",
                }
            },
            start_conditions=["Request input is validated but specialist routing is ambiguous."],
            depends_on=[],
            result_handoff_condition=(
                "Forward the result when a single specialist domain is selected "
                "with an explicit rationale."
            ),
            required_input_context=base_context,
            expected_result=(
                "Workflow routing ambiguity is resolved before specialist delegation."
            ),
            status=WorkflowStepStatus.BLOCKED,
            risk_flags=plan_risk_flags,
            requires_user_approval=False,
        )

    if operation_type in {
        OperationType.DEPLOY,
        OperationType.ROLLBACK,
        OperationType.RESTART,
    }:
        return build_plan_step(
            step_order=step_order,
            owner_agent=SpecialistAgentName.DEPLOYMENT_AGENT,
            task_type=AgentTaskType.SERVICE_ROLLOUT,
            task_description="Prepare the service rollout or recovery strategy.",
            agent_instruction=(
                "Create the service-level rollout strategy for the requested "
                "operation, including sequencing, rollback readiness, and service "
                "availability expectations."
            ),
            expected_output_json_format=build_specialist_result_format(
                focus="service_rollout"
            ),
            start_conditions=["Required specialist analyses completed."],
            depends_on=depends_on,
            result_handoff_condition=(
                "Forward the result when the rollout or recovery strategy clearly "
                "maps actions, prerequisites, and rollback handling in JSON."
            ),
            required_input_context=base_context,
            expected_result=(
                "Service rollout strategy is aligned with environment, release "
                "parameters, and validation constraints."
            ),
            status=WorkflowStepStatus.PLANNED,
            risk_flags=plan_risk_flags,
            requires_user_approval=False,
        )

    if operation_type in {OperationType.SCALE, OperationType.CONFIGURE}:
        return build_plan_step(
            step_order=step_order,
            owner_agent=SpecialistAgentName.INFRA_AGENT,
            task_type=AgentTaskType.ENVIRONMENT_CHANGE,
            task_description="Prepare the environment change procedure.",
            agent_instruction=(
                "Translate the requested infrastructure or configuration change "
                "into an ordered environment procedure with dependency checks and "
                "post-change validation points."
            ),
            expected_output_json_format=build_specialist_result_format(
                focus="environment_change"
            ),
            start_conditions=["Required specialist analyses completed."],
            depends_on=depends_on,
            result_handoff_condition=(
                "Forward the result when the environment change procedure defines "
                "ordered actions, dependencies, and validation points in JSON."
            ),
            required_input_context=base_context,
            expected_result=(
                "Environment change procedure is ready for risk and policy review."
            ),
            status=WorkflowStepStatus.PLANNED,
            risk_flags=plan_risk_flags,
            requires_user_approval=False,
        )

    if operation_type in {
        OperationType.PIPELINE,
        OperationType.BUILD,
        OperationType.TEST,
        OperationType.RELEASE,
    }:
        return build_plan_step(
            step_order=step_order,
            owner_agent=SpecialistAgentName.CI_CD_AGENT,
            task_type=AgentTaskType.PIPELINE_PROCEDURE,
            task_description="Prepare the pipeline or release-flow procedure.",
            agent_instruction=(
                "Convert the requested CI/CD operation into an ordered pipeline "
                "or release-flow procedure with required checks, artifacts, and "
                "promotion criteria."
            ),
            expected_output_json_format=build_specialist_result_format(
                focus="pipeline_procedure"
            ),
            start_conditions=["Required specialist analyses completed."],
            depends_on=depends_on,
            result_handoff_condition=(
                "Forward the result when the pipeline procedure defines checks, "
                "artifacts, and promotion criteria in JSON."
            ),
            required_input_context=base_context,
            expected_result=(
                "Pipeline or release-flow procedure is ready for risk and policy review."
            ),
            status=WorkflowStepStatus.PLANNED,
            risk_flags=plan_risk_flags,
            requires_user_approval=False,
        )

    return build_plan_step(
        step_order=step_order,
        owner_agent=resolve_diagnostic_owner(routing_decision),
        task_type=AgentTaskType.DIAGNOSTIC_PLAN,
        task_description="Prepare the diagnostic investigation plan.",
        agent_instruction=(
            "Build a diagnostic investigation plan that identifies likely failure "
            "domains, required evidence, and non-invasive verification steps."
        ),
        expected_output_json_format=build_specialist_result_format(
            focus="diagnostic_plan"
        ),
        start_conditions=["Required specialist analyses completed."],
        depends_on=depends_on,
        result_handoff_condition=(
            "Forward the result when the diagnostic plan lists hypotheses, evidence "
            "requests, and verification steps in JSON."
        ),
        required_input_context=base_context,
        expected_result=(
            "Diagnostic investigation plan is ready for aggregation and policy review."
        ),
        status=WorkflowStepStatus.PLANNED,
        risk_flags=plan_risk_flags,
        requires_user_approval=False,
    )


def build_domain_analysis_step(
    *,
    task_request: TaskRequest,
    domain: SpecialistDomain,
    base_context: dict[str, Any],
    plan_risk_flags: list[str],
    step_order: int,
) -> WorkflowPlanStep:
    if domain == SpecialistDomain.DEPLOYMENT:
        return build_plan_step(
            step_order=step_order,
            owner_agent=SpecialistAgentName.DEPLOYMENT_AGENT,
            task_type=AgentTaskType.DEPLOYMENT_ANALYSIS,
            task_description="Analyze deployment impact and rollout prerequisites.",
            agent_instruction=build_deployment_analysis_instruction(task_request),
            expected_output_json_format=build_specialist_result_format(focus="deployment"),
            start_conditions=["Request input is validated and ready for planning."],
            depends_on=[],
            result_handoff_condition=(
                "Forward the result when deployment prerequisites, rollout notes, "
                "and proposed actions are returned in JSON."
            ),
            required_input_context=base_context,
            expected_result=(
                "Deployment analysis defines rollout prerequisites, service impact, "
                "and executable recommendations."
            ),
            status=WorkflowStepStatus.PLANNED,
            risk_flags=plan_risk_flags,
            requires_user_approval=False,
        )

    if domain == SpecialistDomain.CI_CD:
        return build_plan_step(
            step_order=step_order,
            owner_agent=SpecialistAgentName.CI_CD_AGENT,
            task_type=AgentTaskType.CI_CD_ANALYSIS,
            task_description="Analyze CI/CD impact, validation gates, and artifact flow.",
            agent_instruction=build_ci_cd_analysis_instruction(task_request),
            expected_output_json_format=build_specialist_result_format(focus="ci_cd"),
            start_conditions=["Request input is validated and ready for planning."],
            depends_on=[],
            result_handoff_condition=(
                "Forward the result when pipeline checks, test expectations, "
                "and release-flow recommendations are returned in JSON."
            ),
            required_input_context=base_context,
            expected_result=(
                "CI/CD analysis defines pipeline implications, required validation, "
                "and artifact or release-flow actions."
            ),
            status=WorkflowStepStatus.PLANNED,
            risk_flags=plan_risk_flags,
            requires_user_approval=False,
        )

    return build_plan_step(
        step_order=step_order,
        owner_agent=SpecialistAgentName.INFRA_AGENT,
        task_type=AgentTaskType.INFRASTRUCTURE_ANALYSIS,
        task_description="Analyze infrastructure dependencies and environment impact.",
        agent_instruction=build_infrastructure_analysis_instruction(task_request),
        expected_output_json_format=build_specialist_result_format(focus="infrastructure"),
        start_conditions=["Request input is validated and ready for planning."],
        depends_on=[],
        result_handoff_condition=(
            "Forward the result when infrastructure dependencies, risks, "
            "and proposed actions are returned in JSON."
        ),
        required_input_context=base_context,
        expected_result=(
            "Infrastructure analysis identifies environment dependencies, "
            "configuration impact, and required follow-up actions."
        ),
        status=WorkflowStepStatus.PLANNED,
        risk_flags=plan_risk_flags,
        requires_user_approval=False,
    )


def build_plan_step(
    *,
    step_order: int,
    owner_agent: SpecialistAgentName,
    task_type: AgentTaskType,
    task_description: str,
    agent_instruction: str,
    expected_output_json_format: dict[str, Any],
    start_conditions: list[str],
    depends_on: list[str],
    result_handoff_condition: str,
    required_input_context: dict[str, Any],
    expected_result: str,
    status: WorkflowStepStatus,
    risk_flags: list[str],
    requires_user_approval: bool,
) -> WorkflowPlanStep:
    return WorkflowPlanStep(
        step_id=f"STEP-{step_order}",
        owner_agent=owner_agent,
        task_type=task_type,
        task_description=task_description,
        agent_instruction=agent_instruction,
        step_order=step_order,
        depends_on=depends_on,
        expected_output_json_format=expected_output_json_format,
        start_conditions=start_conditions,
        result_handoff_condition=result_handoff_condition,
        required_input_context=required_input_context,
        expected_result=expected_result,
        status=status,
        risk_flags=risk_flags,
        requires_user_approval=requires_user_approval,
    )


def resolve_diagnostic_owner(routing_decision: TaskRoutingDecision) -> SpecialistAgentName:
    if routing_decision.primary_domain == SpecialistDomain.DEPLOYMENT:
        return SpecialistAgentName.DEPLOYMENT_AGENT
    if routing_decision.primary_domain == SpecialistDomain.CI_CD:
        return SpecialistAgentName.CI_CD_AGENT
    return SpecialistAgentName.INFRA_AGENT
