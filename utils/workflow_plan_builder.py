from __future__ import annotations

from typing import Any

from contracts.agent_input import AgentTaskType
from contracts.task_request import TaskRequest
from contracts.task_response import (
    SpecialistAgentName,
    WorkflowPlanStep,
    WorkflowStepStatus,
)
from contracts.workflow_routing import (
    RoutingDecisionType,
    SpecialistDomain,
    TaskRoutingDecision,
)
from utils.workflow_plan_templates import (
    build_execution_handoff_instruction,
    build_final_report_instruction,
    build_human_approval_instruction,
    build_risk_policy_instruction,
)
from utils.workflow_step_factory import (
    build_domain_analysis_step,
    build_plan_step,
    build_task_specific_step,
)
from utils.workflow_risk import WorkflowRiskAssessment, assess_workflow_risk
from utils.workflow_routing import (
    build_routing_context,
    build_routing_risk_flags,
    build_task_routing_decision,
)


def build_workflow_plan(task_request: TaskRequest) -> list[WorkflowPlanStep]:
    risk_assessment = assess_workflow_risk(task_request)
    routing_decision = build_task_routing_decision(task_request)
    base_context = build_base_context(task_request, routing_decision)
    plan_risk_flags = combine_plan_risk_flags(risk_assessment, routing_decision)

    steps = build_analysis_steps(
        task_request=task_request,
        routing_decision=routing_decision,
        base_context=base_context,
        plan_risk_flags=plan_risk_flags,
    )

    task_specific_step = build_task_specific_step(
        task_request=task_request,
        routing_decision=routing_decision,
        base_context=base_context,
        plan_risk_flags=plan_risk_flags,
        step_order=len(steps) + 1,
        depends_on=[step.step_id for step in steps],
    )
    steps.append(task_specific_step)

    if routing_decision.requires_human_resolution:
        steps.append(
            build_plan_step(
                step_order=len(steps) + 1,
                owner_agent=SpecialistAgentName.HUMAN_REVIEW_INTERFACE,
                task_type=AgentTaskType.FINAL_REPORT,
                task_description="Prepare a blocked final report explaining the routing ambiguity.",
                agent_instruction=(
                    "Prepare the final structured report payload for the blocked "
                    "workflow state and return JSON only."
                ),
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
                    "Routing ambiguity is recorded and no specialist execution started."
                ],
                depends_on=[task_specific_step.step_id],
                result_handoff_condition=(
                    "Forward the result when the report explains why routing could "
                    "not continue and what clarification is required."
                ),
                required_input_context={
                    **base_context,
                    "aggregation_ready_after": task_specific_step.step_id,
                },
                expected_result=(
                    "Final report payload explains the blocked workflow caused by "
                    "ambiguous specialist routing."
                ),
                status=WorkflowStepStatus.PLANNED,
                risk_flags=plan_risk_flags,
                requires_user_approval=False,
            )
        )
        return steps

    specialist_step_ids = [step.step_id for step in steps]
    risk_review_step_order = len(steps) + 1

    steps.append(
        build_plan_step(
            step_order=risk_review_step_order,
            owner_agent=SpecialistAgentName.RISK_POLICY_AGENT,
            task_type=AgentTaskType.RISK_POLICY_REVIEW,
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
                "aggregated_risk_flags": plan_risk_flags,
                "specialist_steps": specialist_step_ids,
            },
            expected_result=(
                "Risk and policy review classifies each proposed action as allowed, "
                "blocked, or requiring approval."
            ),
            status=WorkflowStepStatus.PLANNED,
            risk_flags=plan_risk_flags,
            requires_user_approval=False,
        )
    )

    if risk_assessment.requires_user_approval:
        human_approval_step_order = len(steps) + 1
        steps.append(
            build_plan_step(
                step_order=human_approval_step_order,
                owner_agent=SpecialistAgentName.HUMAN_REVIEW_INTERFACE,
                task_type=AgentTaskType.HUMAN_APPROVAL,
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
                depends_on=[f"STEP-{risk_review_step_order}"],
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
                risk_flags=plan_risk_flags,
                requires_user_approval=True,
            )
        )

    execution_step_order = len(steps) + 1
    execution_dependencies = (
        [f"STEP-{execution_step_order - 1}"]
        if risk_assessment.requires_user_approval
        else [f"STEP-{risk_review_step_order}"]
    )
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
            step_order=execution_step_order,
            owner_agent=SpecialistAgentName.EXECUTION_AGENT,
            task_type=AgentTaskType.EXECUTION_HANDOFF,
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
                "policy_decision_step": f"STEP-{risk_review_step_order}",
            },
            expected_result=(
                "Execution handoff contains only actions allowed by policy and, when "
                "required, approved by a human reviewer."
            ),
            status=execution_status,
            risk_flags=plan_risk_flags,
            requires_user_approval=False,
        )
    )

    final_report_step_order = len(steps) + 1
    final_dependency = (
        f"STEP-{execution_step_order - 1}"
        if risk_assessment.requires_user_approval
        else f"STEP-{risk_review_step_order}"
    )
    steps.append(
        build_plan_step(
            step_order=final_report_step_order,
            owner_agent=SpecialistAgentName.HUMAN_REVIEW_INTERFACE,
            task_type=AgentTaskType.FINAL_REPORT,
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
            risk_flags=plan_risk_flags,
            requires_user_approval=False,
        )
    )

    return steps


def build_analysis_steps(
    *,
    task_request: TaskRequest,
    routing_decision: TaskRoutingDecision,
    base_context: dict[str, Any],
    plan_risk_flags: list[str],
) -> list[WorkflowPlanStep]:
    if routing_decision.decision_type == RoutingDecisionType.AMBIGUOUS:
        return []

    analysis_steps: list[WorkflowPlanStep] = []
    for step_order, domain in enumerate(
        [routing_decision.primary_domain, *routing_decision.supporting_domains],
        start=1,
    ):
        if domain is None:
            continue
        analysis_steps.append(
            build_domain_analysis_step(
                task_request=task_request,
                domain=domain,
                base_context=base_context,
                plan_risk_flags=plan_risk_flags,
                step_order=step_order,
            )
        )
    return analysis_steps


def combine_plan_risk_flags(
    risk_assessment: WorkflowRiskAssessment,
    routing_decision: TaskRoutingDecision,
) -> list[str]:
    combined_flags = risk_assessment.risk_flags + build_routing_risk_flags(routing_decision)
    return list(dict.fromkeys(combined_flags))


def build_base_context(
    task_request: TaskRequest, routing_decision: TaskRoutingDecision
) -> dict[str, Any]:
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
        "routing": build_routing_context(routing_decision),
    }
