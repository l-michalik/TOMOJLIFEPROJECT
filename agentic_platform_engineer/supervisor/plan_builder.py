from __future__ import annotations

from agentic_platform_engineer.contracts.supervisor_input import (
    IntakeStatus,
    JsonValue,
    RequestSource,
)
from agentic_platform_engineer.contracts.supervisor_intake import (
    OperationType,
    SupervisorTaskClass,
    SupervisorWorkItem,
)
from agentic_platform_engineer.contracts.supervisor_plan import (
    PlanStatus,
    PlanStep,
    PlanStepStatus,
    SupervisorPlan,
    SupervisorPlanBuildResult,
    TargetAgent,
)


def build_supervisor_plan(work_item: SupervisorWorkItem) -> SupervisorPlanBuildResult:
    if work_item.intake.status is not IntakeStatus.READY_FOR_PLANNING:
        return SupervisorPlanBuildResult(
            plan=SupervisorPlan(
                request_id=work_item.request_id,
                status=PlanStatus.NEEDS_CLARIFICATION,
            ),
            intake=work_item.intake,
            planning_block_reason="Supervisor cannot create a plan until intake is ready for planning.",
        )

    steps = (
        _build_deployment_analysis_step(work_item),
        _build_infra_analysis_step(work_item),
        _build_ci_analysis_step(work_item),
        *_build_operation_specific_steps(work_item),
    )
    return SupervisorPlanBuildResult(
        plan=SupervisorPlan(
            request_id=work_item.request_id,
            status=PlanStatus.PLANNED,
            steps=tuple(steps),
        ),
        intake=work_item.intake,
        planned_actions_hint=_build_planned_actions_hint(work_item),
    )


def _build_deployment_analysis_step(work_item: SupervisorWorkItem) -> PlanStep:
    return PlanStep(
        step_id="step-1",
        name="deployment_analysis",
        target_agent=TargetAgent.DEPLOYMENT,
        instruction=_build_agent_instruction(
            work_item,
            target_agent=TargetAgent.DEPLOYMENT,
            objective="Analyze deployment scope, release dependencies, service rollout needs, and deployment risks.",
            responsibilities=(
                "Determine whether the request changes application release state.",
                "Describe deployment prerequisites, rollout implications, and rollback considerations.",
                "Return planned deployment actions without executing them.",
            ),
        ),
        expected_response_format=_build_expected_response_format(
            domain="deployment",
            required_findings=("deployment_scope", "deployment_dependencies", "planned_actions"),
        ),
        start_condition="Start when the normalized work item is ready for planning.",
        aggregation_condition="Aggregate this result when the agent returns valid JSON with planned_actions and status.",
        status=PlanStepStatus.PENDING,
    )


def _build_infra_analysis_step(work_item: SupervisorWorkItem) -> PlanStep:
    return PlanStep(
        step_id="step-2",
        name="infrastructure_analysis",
        target_agent=TargetAgent.INFRA,
        instruction=_build_agent_instruction(
            work_item,
            target_agent=TargetAgent.INFRA,
            objective="Analyze infrastructure dependencies, environment constraints, and infrastructure-side planned actions.",
            responsibilities=(
                "Check environment dependencies, configuration needs, and infrastructure blockers.",
                "Identify infrastructure actions implied by the request.",
                "Return only analysis results and planned actions for policy review.",
            ),
        ),
        expected_response_format=_build_expected_response_format(
            domain="infrastructure",
            required_findings=("infrastructure_scope", "environment_dependencies", "planned_actions"),
        ),
        start_condition="Start after deployment analysis context is available or immediately if no deployment context is required.",
        dependencies=("step-1",),
        aggregation_condition="Aggregate this result when dependencies are satisfied and the response contains planned_actions.",
        status=PlanStepStatus.PENDING,
    )


def _build_ci_analysis_step(work_item: SupervisorWorkItem) -> PlanStep:
    return PlanStep(
        step_id="step-3",
        name="ci_cd_analysis",
        target_agent=TargetAgent.CI_CD,
        instruction=_build_agent_instruction(
            work_item,
            target_agent=TargetAgent.CI_CD,
            objective="Analyze pipeline, artifact, and release-flow implications of the request.",
            responsibilities=(
                "Validate pipeline prerequisites, artifact expectations, and CI/CD blockers.",
                "Identify CI/CD planned actions needed before execution.",
                "Return structured analysis and planned actions only.",
            ),
        ),
        expected_response_format=_build_expected_response_format(
            domain="ci_cd",
            required_findings=("pipeline_scope", "artifact_requirements", "planned_actions"),
        ),
        start_condition="Start when the work item includes enough request context for pipeline analysis.",
        aggregation_condition="Aggregate this result when the response is valid JSON and contains status, summary, and planned_actions.",
        status=PlanStepStatus.PENDING,
    )


def _build_operation_specific_steps(work_item: SupervisorWorkItem) -> tuple[PlanStep, ...]:
    if work_item.operation_type in {OperationType.DEPLOY, OperationType.ROLLBACK}:
        return (_build_deployment_planning_step(work_item),)
    if work_item.operation_type in {OperationType.INFRA_CHANGE, OperationType.INFRA_PROVISION}:
        return (_build_infrastructure_planning_step(work_item),)
    if work_item.operation_type in {OperationType.PIPELINE_RUN, OperationType.PIPELINE_VALIDATE}:
        return (_build_ci_planning_step(work_item),)
    return ()


def _build_deployment_planning_step(work_item: SupervisorWorkItem) -> PlanStep:
    return PlanStep(
        step_id="step-4",
        name="deployment_operation_plan",
        target_agent=TargetAgent.DEPLOYMENT,
        instruction=_build_agent_instruction(
            work_item,
            target_agent=TargetAgent.DEPLOYMENT,
            objective="Prepare the deployment-specific execution plan for policy review.",
            responsibilities=(
                "Synthesize deployment, infrastructure, and CI/CD findings into deployment-oriented planned actions.",
                "Respect constraints, target environment, and rollout parameters from the work item.",
                "Return a policy-reviewable deployment plan without executing changes.",
            ),
        ),
        expected_response_format=_build_expected_response_format(
            domain="deployment_plan",
            required_findings=("planned_actions", "rollback_strategy", "risk_notes"),
        ),
        start_condition="Start after deployment, infrastructure, and CI/CD analysis steps have produced their findings.",
        dependencies=("step-1", "step-2", "step-3"),
        aggregation_condition="Aggregate this result when all prerequisite analysis steps are completed and the response lists planned_actions.",
        status=PlanStepStatus.PENDING,
    )


def _build_infrastructure_planning_step(work_item: SupervisorWorkItem) -> PlanStep:
    return PlanStep(
        step_id="step-4",
        name="infrastructure_operation_plan",
        target_agent=TargetAgent.INFRA,
        instruction=_build_agent_instruction(
            work_item,
            target_agent=TargetAgent.INFRA,
            objective="Prepare the infrastructure-specific execution plan for policy review.",
            responsibilities=(
                "Turn infrastructure findings into explicit infrastructure planned actions.",
                "Include environment constraints, reversibility notes, and deployment interactions.",
                "Return a policy-reviewable infrastructure plan without executing changes.",
            ),
        ),
        expected_response_format=_build_expected_response_format(
            domain="infrastructure_plan",
            required_findings=("planned_actions", "change_scope", "risk_notes"),
        ),
        start_condition="Start after deployment and infrastructure analysis steps are available.",
        dependencies=("step-1", "step-2"),
        aggregation_condition="Aggregate this result when prerequisite analysis is complete and the response includes planned_actions.",
        status=PlanStepStatus.PENDING,
    )


def _build_ci_planning_step(work_item: SupervisorWorkItem) -> PlanStep:
    return PlanStep(
        step_id="step-4",
        name="ci_cd_operation_plan",
        target_agent=TargetAgent.CI_CD,
        instruction=_build_agent_instruction(
            work_item,
            target_agent=TargetAgent.CI_CD,
            objective="Prepare the CI/CD-specific execution plan for policy review.",
            responsibilities=(
                "Turn CI/CD findings into explicit pipeline or release-flow planned actions.",
                "Include artifact expectations, environment interactions, and gating requirements.",
                "Return a policy-reviewable CI/CD plan without executing changes.",
            ),
        ),
        expected_response_format=_build_expected_response_format(
            domain="ci_cd_plan",
            required_findings=("planned_actions", "pipeline_gates", "risk_notes"),
        ),
        start_condition="Start after the CI/CD analysis step is completed and any required environment context is available.",
        dependencies=("step-3",),
        aggregation_condition="Aggregate this result when prerequisite analysis is complete and the response includes planned_actions.",
        status=PlanStepStatus.PENDING,
    )


def _build_agent_instruction(
    work_item: SupervisorWorkItem,
    *,
    target_agent: TargetAgent,
    objective: str,
    responsibilities: tuple[str, ...],
) -> str:
    lines = [
        f"You are {target_agent.value}.",
        objective,
        f"Request ID: {work_item.request_id}.",
        f"Source: {_format_source(work_item.source)}.",
        f"User request: {work_item.user_request}.",
        f"Task class: {work_item.task_class.value if work_item.task_class is not None else 'unknown'}.",
        f"Operation type: {work_item.operation_type.value if work_item.operation_type is not None else 'unknown'}.",
        f"Service: {work_item.service_name or 'not provided'}.",
        f"Target environment: {work_item.target_environment.value if work_item.target_environment is not None else 'not provided'}.",
        f"Priority: {work_item.priority.value if work_item.priority is not None else 'not provided'}.",
        f"Execution params: {work_item.execution_params}.",
        f"Constraints: {list(work_item.constraints)}.",
        "Do not execute changes. Return analysis and planned actions only.",
    ]
    lines.extend(f"Responsibility: {item}" for item in responsibilities)
    return "\n".join(lines)


def _build_expected_response_format(
    *,
    domain: str,
    required_findings: tuple[str, ...],
) -> dict[str, JsonValue]:
    return {
        "status": "success|needs_clarification|blocked",
        "domain": domain,
        "summary": "string",
        "findings": list(required_findings),
        "planned_actions": [
            {
                "action_id": "string",
                "description": "string",
                "target": "string",
                "requires_policy_review": True,
            }
        ],
        "risks": ["string"],
        "missing_information": ["string"],
    }


def _build_planned_actions_hint(work_item: SupervisorWorkItem) -> tuple[str, ...]:
    if work_item.operation_type is OperationType.DEPLOY:
        return ("deployment_plan", "risk_policy_review")
    if work_item.operation_type is OperationType.ROLLBACK:
        return ("rollback_plan", "risk_policy_review")
    if work_item.operation_type in {OperationType.INFRA_CHANGE, OperationType.INFRA_PROVISION}:
        return ("infrastructure_plan", "risk_policy_review")
    if work_item.operation_type in {OperationType.PIPELINE_RUN, OperationType.PIPELINE_VALIDATE}:
        return ("ci_cd_plan", "risk_policy_review")
    return ("risk_policy_review",)


def _format_source(source: RequestSource | None) -> str:
    if source is None:
        return "unknown"
    return source.value
