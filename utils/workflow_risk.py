from __future__ import annotations

from dataclasses import dataclass

from contracts.task_request import OperationType, TaskRequest, TargetEnvironment


@dataclass(frozen=True)
class WorkflowRiskAssessment:
    risk_flags: list[str]
    requires_user_approval: bool


def build_workflow_confidence(task_request: TaskRequest) -> float:
    confidence = 0.96
    constraints = set(task_request.standardized_work_item.constraints)
    if task_request.standardized_work_item.target_environment == TargetEnvironment.PROD:
        confidence -= 0.06
    if task_request.standardized_work_item.operation_type in {
        OperationType.ROLLBACK,
        OperationType.RESTART,
        OperationType.CONFIGURE,
        OperationType.SCALE,
        OperationType.DIAGNOSE,
    }:
        confidence -= 0.04
    if "requires_approval" in constraints or "outside_business_hours" in constraints:
        confidence -= 0.03
    return max(0.7, round(confidence, 2))


def assess_workflow_risk(task_request: TaskRequest) -> WorkflowRiskAssessment:
    work_item = task_request.standardized_work_item
    risk_flags: list[str] = []

    if work_item.target_environment == TargetEnvironment.PROD:
        risk_flags.append("production_change")
    if work_item.operation_type in {
        OperationType.ROLLBACK,
        OperationType.RESTART,
        OperationType.CONFIGURE,
        OperationType.SCALE,
    }:
        risk_flags.append("elevated_operational_risk")
    if work_item.operation_type == OperationType.DIAGNOSE:
        risk_flags.append("investigation_required")

    for constraint in work_item.constraints:
        if constraint == "requires_approval":
            risk_flags.append("explicit_approval_required")
        if constraint == "outside_business_hours":
            risk_flags.append("restricted_execution_window")
        if constraint == "no_downtime":
            risk_flags.append("availability_constraint")

    deduplicated_risk_flags = list(dict.fromkeys(risk_flags))
    requires_user_approval = (
        "production_change" in deduplicated_risk_flags
        or "explicit_approval_required" in deduplicated_risk_flags
    )
    return WorkflowRiskAssessment(
        risk_flags=deduplicated_risk_flags,
        requires_user_approval=requires_user_approval,
    )
