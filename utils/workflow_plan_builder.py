from __future__ import annotations

from typing import Any

from contracts.task_request import OperationType, TaskRequest
from contracts.task_response import (
    SpecialistAgentName,
    WorkflowPlanStep,
    WorkflowStepStatus,
)
from utils.workflow_plan_templates import (
    build_ci_cd_analysis_instruction,
    build_deployment_analysis_instruction,
    build_execution_handoff_instruction,
    build_final_report_instruction,
    build_human_approval_instruction,
    build_infrastructure_analysis_instruction,
    build_risk_policy_instruction,
    build_specialist_result_format,
)
from utils.workflow_risk import WorkflowRiskAssessment, assess_workflow_risk


def build_workflow_plan(task_request: TaskRequest) -> list[WorkflowPlanStep]:
    work_item = task_request.standardized_work_item
    risk_assessment = assess_workflow_risk(task_request)
    base_context = build_base_context(task_request)

    steps: list[WorkflowPlanStep] = [
        build_plan_step(
            step_order=1,
            owner_agent=SpecialistAgentName.DEPLOYMENT_AGENT,
            task_description="Analyze deployment impact and rollout prerequisites.",
            agent_instruction=build_deployment_analysis_instruction(task_request),
            expected_output_json_format=build_specialist_result_format(
                focus="deployment"
            ),
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
            risk_flags=risk_assessment.risk_flags,
            requires_user_approval=False,
        ),
        build_plan_step(
            step_order=2,
            owner_agent=SpecialistAgentName.INFRA_AGENT,
            task_description="Analyze infrastructure dependencies and environment impact.",
            agent_instruction=build_infrastructure_analysis_instruction(task_request),
            expected_output_json_format=build_specialist_result_format(
                focus="infrastructure"
            ),
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
            risk_flags=risk_assessment.risk_flags,
            requires_user_approval=False,
        ),
        build_plan_step(
            step_order=3,
            owner_agent=SpecialistAgentName.CI_CD_AGENT,
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
            risk_flags=risk_assessment.risk_flags,
            requires_user_approval=False,
        ),
    ]

    task_specific_step = build_task_specific_step(
        task_request=task_request,
        risk_assessment=risk_assessment,
        base_context=base_context,
    )
    steps.append(task_specific_step)

    specialist_step_ids = [step.step_id for step in steps]

    steps.append(
        build_plan_step(
            step_order=5,
            owner_agent=SpecialistAgentName.RISK_POLICY_AGENT,
            task_description="Review proposed actions against risk and policy gates.",
            agent_instruction=build_risk_policy_instruction(task_request),
            expected_output_json_format={
                "decisions": [
                    {
                        "action_id": "string",
                        "allowed": True,
                        "requires_approval": False,
                        "reason": "string",
                        "applied_policies": ["string"],
                    }
                ]
            },
            start_conditions=[
                "All specialist analysis steps completed and returned JSON results."
            ],
            depends_on=specialist_step_ids,
            result_handoff_condition=(
                "Forward the result when every proposed action has an explicit policy "
                "decision and approval requirement."
            ),
            required_input_context={
                "actions": [],
                "environment": base_context["target_environment"],
                "operation_type": base_context["operation_type"],
                "business_context": {
                    key: value
                    for key, value in {
                        "request_id": task_request.request_id,
                        "source": task_request.source.value,
                        "priority": base_context["priority"],
                        "service_name": base_context["service_name"],
                        "ticket_id": task_request.params.ticket_id,
                        "conversation_id": task_request.params.conversation_id,
                        "user_request": task_request.user_request,
                    }.items()
                    if value is not None
                },
                "aggregated_risk_flags": risk_assessment.risk_flags,
                "specialist_steps": specialist_step_ids,
            },
            expected_result=(
                "Risk and policy review classifies each proposed action as allowed, "
                "blocked, or requiring approval."
            ),
            status=WorkflowStepStatus.PLANNED,
            risk_flags=risk_assessment.risk_flags,
            requires_user_approval=False,
        )
    )

    if risk_assessment.requires_user_approval:
        steps.append(
            build_plan_step(
                step_order=6,
                owner_agent=SpecialistAgentName.HUMAN_REVIEW_INTERFACE,
                task_description="Request human approval for gated actions.",
                agent_instruction=build_human_approval_instruction(task_request),
                expected_output_json_format={
                    "approval_decision": {
                        "status": "approved|rejected",
                        "decision_by": "string",
                        "decision_reason": "string",
                    }
                },
                start_conditions=[
                    "Risk/Policy Agent returned at least one action requiring approval."
                ],
                depends_on=["STEP-5"],
                result_handoff_condition=(
                    "Forward the result when a final human decision is recorded for "
                    "all approval-gated actions."
                ),
                required_input_context={
                    **base_context,
                    "approval_required_for": risk_assessment.risk_flags,
                },
                expected_result=(
                    "Human review produces an explicit approval or rejection decision "
                    "for gated actions."
                ),
                status=WorkflowStepStatus.WAITING_FOR_APPROVAL,
                risk_flags=risk_assessment.risk_flags,
                requires_user_approval=True,
            )
        )

    execution_dependencies = ["STEP-6"] if risk_assessment.requires_user_approval else ["STEP-5"]
    execution_status = (
        WorkflowStepStatus.BLOCKED
        if risk_assessment.requires_user_approval
        else WorkflowStepStatus.PLANNED
    )
    execution_start_conditions = [
        "Risk/Policy Agent marked the action set as allowed for execution."
    ]
    if risk_assessment.requires_user_approval:
        execution_start_conditions.append(
            "Human approval is granted for all approval-gated actions."
        )

    steps.append(
        build_plan_step(
            step_order=7 if risk_assessment.requires_user_approval else 6,
            owner_agent=SpecialistAgentName.EXECUTION_AGENT,
            task_description="Prepare approved actions for execution handoff.",
            agent_instruction=build_execution_handoff_instruction(task_request),
            expected_output_json_format={
                "execution_handoff": {
                    "approved_actions": ["string"],
                    "blocked_actions": ["string"],
                    "required_tools": ["string"],
                }
            },
            start_conditions=execution_start_conditions,
            depends_on=execution_dependencies,
            result_handoff_condition=(
                "Forward the result when the approved action list is complete and "
                "ready for controlled execution."
            ),
            required_input_context={
                **base_context,
                "policy_decision_step": "STEP-5",
            },
            expected_result=(
                "Execution handoff contains only actions allowed by policy and, when "
                "required, approved by a human reviewer."
            ),
            status=execution_status,
            risk_flags=risk_assessment.risk_flags,
            requires_user_approval=False,
        )
    )

    final_dependency = "STEP-6" if risk_assessment.requires_user_approval else "STEP-5"
    steps.append(
        build_plan_step(
            step_order=8 if risk_assessment.requires_user_approval else 7,
            owner_agent=SpecialistAgentName.HUMAN_REVIEW_INTERFACE,
            task_description="Prepare final report payload for aggregation and publication.",
            agent_instruction=build_final_report_instruction(task_request),
            expected_output_json_format={
                "final_report": {
                    "summary": "string",
                    "executed_actions": ["string"],
                    "blocked_actions": ["string"],
                    "approvals": ["string"],
                    "artifacts": ["string"],
                }
            },
            start_conditions=[
                "Specialist analysis is aggregated and policy outcome is available."
            ],
            depends_on=[final_dependency],
            result_handoff_condition=(
                "Forward the result when the report includes summary, approvals, "
                "blocked actions, and artifact references in JSON."
            ),
            required_input_context={
                **base_context,
                "aggregation_ready_after": final_dependency,
            },
            expected_result=(
                "Final report payload is ready for Supervisor aggregation and delivery "
                "to the source channel."
            ),
            status=WorkflowStepStatus.PLANNED,
            risk_flags=risk_assessment.risk_flags,
            requires_user_approval=False,
        )
    )

    return steps
def build_task_specific_step(
    task_request: TaskRequest,
    risk_assessment: WorkflowRiskAssessment,
    base_context: dict[str, Any],
) -> WorkflowPlanStep:
    operation_type = task_request.standardized_work_item.operation_type

    if operation_type in {
        OperationType.DEPLOY,
        OperationType.ROLLBACK,
        OperationType.RESTART,
    }:
        return build_plan_step(
            step_order=4,
            owner_agent=SpecialistAgentName.DEPLOYMENT_AGENT,
            task_description="Prepare the service rollout or recovery strategy.",
            agent_instruction=(
                "Create the service-level rollout strategy for the requested "
                "operation, including sequencing, rollback readiness, and service "
                "availability expectations."
            ),
            expected_output_json_format=build_specialist_result_format(
                focus="service_rollout"
            ),
            start_conditions=[
                "Deployment analysis, infrastructure analysis, and CI/CD analysis started."
            ],
            depends_on=["STEP-1", "STEP-2", "STEP-3"],
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
            risk_flags=risk_assessment.risk_flags,
            requires_user_approval=False,
        )

    if operation_type in {OperationType.SCALE, OperationType.CONFIGURE}:
        return build_plan_step(
            step_order=4,
            owner_agent=SpecialistAgentName.INFRA_AGENT,
            task_description="Prepare the environment change procedure.",
            agent_instruction=(
                "Translate the requested infrastructure or configuration change "
                "into an ordered environment procedure with dependency checks and "
                "post-change validation points."
            ),
            expected_output_json_format=build_specialist_result_format(
                focus="environment_change"
            ),
            start_conditions=[
                "Deployment analysis, infrastructure analysis, and CI/CD analysis started."
            ],
            depends_on=["STEP-1", "STEP-2", "STEP-3"],
            result_handoff_condition=(
                "Forward the result when the environment change procedure defines "
                "ordered actions, dependencies, and validation points in JSON."
            ),
            required_input_context=base_context,
            expected_result=(
                "Environment change procedure is ready for risk and policy review."
            ),
            status=WorkflowStepStatus.PLANNED,
            risk_flags=risk_assessment.risk_flags,
            requires_user_approval=False,
        )

    if operation_type in {
        OperationType.PIPELINE,
        OperationType.BUILD,
        OperationType.TEST,
        OperationType.RELEASE,
    }:
        return build_plan_step(
            step_order=4,
            owner_agent=SpecialistAgentName.CI_CD_AGENT,
            task_description="Prepare the pipeline or release-flow procedure.",
            agent_instruction=(
                "Convert the requested CI/CD operation into an ordered pipeline "
                "or release-flow procedure with required checks, artifacts, and "
                "promotion criteria."
            ),
            expected_output_json_format=build_specialist_result_format(
                focus="pipeline_procedure"
            ),
            start_conditions=[
                "Deployment analysis, infrastructure analysis, and CI/CD analysis started."
            ],
            depends_on=["STEP-1", "STEP-2", "STEP-3"],
            result_handoff_condition=(
                "Forward the result when the pipeline procedure defines checks, "
                "artifacts, and promotion criteria in JSON."
            ),
            required_input_context=base_context,
            expected_result=(
                "Pipeline or release-flow procedure is ready for risk and policy review."
            ),
            status=WorkflowStepStatus.PLANNED,
            risk_flags=risk_assessment.risk_flags,
            requires_user_approval=False,
        )

    return build_plan_step(
        step_order=4,
        owner_agent=SpecialistAgentName.INFRA_AGENT,
        task_description="Prepare the diagnostic investigation plan.",
        agent_instruction=(
            "Build a diagnostic investigation plan that identifies likely failure "
            "domains, required evidence, and non-invasive verification steps."
        ),
        expected_output_json_format=build_specialist_result_format(
            focus="diagnostic_plan"
        ),
        start_conditions=[
            "Deployment analysis, infrastructure analysis, and CI/CD analysis started."
        ],
        depends_on=["STEP-1", "STEP-2", "STEP-3"],
        result_handoff_condition=(
            "Forward the result when the diagnostic plan lists hypotheses, evidence "
            "requests, and verification steps in JSON."
        ),
        required_input_context=base_context,
        expected_result=(
            "Diagnostic investigation plan is ready for aggregation and policy review."
        ),
        status=WorkflowStepStatus.PLANNED,
        risk_flags=risk_assessment.risk_flags,
        requires_user_approval=False,
    )


def build_plan_step(
    step_order: int,
    owner_agent: SpecialistAgentName,
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


def build_base_context(task_request: TaskRequest) -> dict[str, Any]:
    work_item = task_request.standardized_work_item
    return {
        "request_id": task_request.request_id,
        "source": task_request.source.value,
        "priority": task_request.params.priority.value if task_request.params.priority else None,
        "service_name": work_item.service_name,
        "target_environment": (
            work_item.target_environment.value if work_item.target_environment else None
        ),
        "operation_type": work_item.operation_type.value if work_item.operation_type else None,
        "execution_parameters": work_item.execution_parameters,
        "constraints": work_item.constraints,
    }
