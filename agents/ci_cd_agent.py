from __future__ import annotations

import json
from typing import Any, Sequence

from deepagents import create_deep_agent

from agents.specialist_base import BaseSpecialistAgent
from contracts.agent_input import AgentExecutionInput, AgentTaskType
from contracts.agent_output import AgentExecutionOutput, AgentExecutionStatus
from settings.supervisor import load_prompt
from utils.specialist_execution_logging import SpecialistExecutionAuditLogger, append_output_audit_event, attach_execution_details

ToolDefinition = Any

PIPELINE_REFERENCE_KEYS = {
    "pipeline_name",
    "pipeline_id",
    "pipeline_file",
    "workflow_name",
    "workflow_id",
    "workflow_file",
    "config_file",
    "ci_file",
}
REPOSITORY_REFERENCE_KEYS = {
    "repository",
    "repository_name",
    "repo",
    "repo_name",
    "project_path",
}
RUN_REFERENCE_KEYS = {
    "run_id",
    "run_number",
    "job_id",
    "job_name",
    "stage_name",
    "build_id",
    "build_number",
}
SOURCE_CONTROL_KEYS = {
    "branch",
    "commit_sha",
    "commit",
    "tag",
    "ref",
}
ARTIFACT_REFERENCE_KEYS = {
    "artifact",
    "artifact_name",
    "artifact_id",
    "artifact_uri",
    "release_version",
    "image",
    "image_tag",
}
LOG_REFERENCE_KEYS = {
    "pipeline_logs",
    "job_logs",
    "log_excerpt",
    "log_excerpts",
    "log_reference",
    "logs_reference",
    "failed_step_logs",
    "test_report_summary",
    "build_output_summary",
}
VALIDATION_CONFIG_KEYS = {
    "config_changes",
    "config_diff",
    "validation_targets",
    "quality_gates",
    "secrets_scope",
    "permissions_scope",
    "trigger_conditions",
    "matrix",
    "stages",
    "jobs",
}
EXECUTION_ONLY_ACTION_TYPES = {
    "job_retry_request",
    "pipeline_update",
    "build_fix",
    "test_fix",
    "artifact_validation",
    "release_gate_review",
    "config_change",
}


class CICDAgent(BaseSpecialistAgent):
    def __init__(
        self,
        *,
        model: str,
        tools: Sequence[ToolDefinition] | None = None,
        deep_agent_factory: Any | None = None,
    ) -> None:
        super().__init__(
            model=model,
            owner_agent="CI_CD_Agent",
            system_prompt=load_prompt("ci_cd_agent.md"),
            agent_name="ci-cd-agent",
            tools=tools,
            request_log_summary="Analyze the CI/CD pipeline and release flow requirements.",
            response_log_summary="CI/CD analysis result received.",
            deep_agent_factory=deep_agent_factory or create_deep_agent,
        )

    def run(self, payload: AgentExecutionInput | dict[str, Any]) -> AgentExecutionOutput:
        try:
            agent_input = AgentExecutionInput.model_validate(payload)
        except Exception as exc:
            audit_logger = SpecialistExecutionAuditLogger(
                owner_agent="CI_CD_Agent",
                input_snapshot=payload,
            )
            audit_logger.record_error(
                summary="CI_CD_Agent input contract validation failed.",
                error={
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                },
            )
            output = self.build_failed_output(
                code="invalid_agent_input",
                category="prompt_error",
                message="Specialist agent input contract validation failed.",
                details={"error": str(exc)},
                recommended_action="mark_failed",
                can_retry=False,
                reason="The step input is invalid, so Supervisor should mark the step as failed.",
            )
            return attach_execution_details(output=output, audit_logger=audit_logger)

        missing_context = identify_missing_ci_cd_context(agent_input)
        if missing_context:
            return build_blocked_ci_cd_output(agent_input, missing_context)
        return super().run(agent_input)

    def build_additional_prompt_sections(
        self,
        agent_input: AgentExecutionInput,
    ) -> list[str]:
        technical_params = agent_input.technical_params
        execution_parameters = dict(technical_params.get("execution_parameters") or {})
        ci_cd_scenario = infer_ci_cd_scenario(agent_input)
        ci_cd_context = {
            "service_name": agent_input.context.service_name,
            "target_environment": agent_input.target_environment.value,
            "task_type": agent_input.task_type.value,
            "operation_type": technical_params.get("operation_type"),
            "ci_cd_scenario": ci_cd_scenario,
            "repository": collect_matching_values(
                technical_params,
                execution_parameters,
                REPOSITORY_REFERENCE_KEYS,
            ),
            "pipeline": collect_matching_values(
                technical_params,
                execution_parameters,
                PIPELINE_REFERENCE_KEYS,
            ),
            "run_context": collect_matching_values(
                technical_params,
                execution_parameters,
                RUN_REFERENCE_KEYS | SOURCE_CONTROL_KEYS | ARTIFACT_REFERENCE_KEYS,
            ),
            "pipeline_log_context": build_pipeline_log_context(
                technical_params,
                execution_parameters,
                agent_input.previous_step_outputs,
            ),
            "validation_scope": infer_validation_scope(technical_params, execution_parameters),
            "depends_on": list(agent_input.depends_on),
            "previous_step_output_ids": sorted(agent_input.previous_step_outputs.keys()),
            "execution_constraints": list(agent_input.execution_constraints),
            "safety_flags": list(agent_input.safety_flags),
        }
        tool_names = [describe_tool(tool) for tool in self.tools]
        return [
            "CI/CD context summary:\n"
            + json.dumps(ci_cd_context, ensure_ascii=True, indent=2),
            "CI/CD tool policy:\n"
            + json.dumps(
                {
                    "allowed_tools": tool_names,
                    "tool_usage_mode": (
                        "inspection_validation_and_log_analysis_only"
                        if tool_names
                        else "analysis_only"
                    ),
                },
                ensure_ascii=True,
                indent=2,
            ),
        ]

    def parse_output(self, raw_text: str) -> AgentExecutionOutput:
        parsed_output = super().parse_output(raw_text)
        if parsed_output.status == AgentExecutionStatus.FAILED:
            return parsed_output

        if not requires_execution_approval(parsed_output.recommended_actions):
            return parsed_output

        if parsed_output.status == AgentExecutionStatus.COMPLETED:
            parsed_output.status = AgentExecutionStatus.WAITING_FOR_APPROVAL
        parsed_output.logs = deduplicate_texts(
            parsed_output.logs
            + ["CI_CD_Agent flagged approval-gated CI/CD actions for Supervisor review."]
        )
        parsed_output.warnings = deduplicate_texts(
            parsed_output.warnings
            + [
                "CI/CD execution-oriented actions require Risk/Policy review and may need human approval."
            ]
        )
        parsed_output.supervisor_data.approval_required_action_ids = deduplicate_texts(
            parsed_output.supervisor_data.approval_required_action_ids
            + [action.action_id for action in parsed_output.recommended_actions]
        )
        parsed_output.supervisor_data.next_decision = "await_policy_and_approval_review"
        append_output_audit_event(
            output=parsed_output,
            owner_agent="CI_CD_Agent",
            summary="CI/CD actions were marked as approval-gated before execution handoff.",
            event_type="decision_recorded",
            payload={
                "decision_type": "approval_gate_applied",
                "approval_required_action_ids": [
                    action.action_id for action in parsed_output.recommended_actions
                ],
            },
            status=parsed_output.status.value,
        )
        return parsed_output


def identify_missing_ci_cd_context(agent_input: AgentExecutionInput) -> list[str]:
    technical_params = agent_input.technical_params
    execution_parameters = dict(technical_params.get("execution_parameters") or {})
    operation_type = str(technical_params.get("operation_type") or "").strip()
    ci_cd_scenario = infer_ci_cd_scenario(agent_input)
    missing_fields: list[str] = []

    if not operation_type:
        missing_fields.append("technical_params.operation_type")
    if not has_any_value(technical_params, execution_parameters, REPOSITORY_REFERENCE_KEYS):
        missing_fields.append("technical_params.execution_parameters.repository")
    if not has_any_value(technical_params, execution_parameters, PIPELINE_REFERENCE_KEYS):
        missing_fields.append("technical_params.execution_parameters.pipeline_name_or_file")

    if ci_cd_scenario in {
        "job_status_analysis",
        "build_failure_diagnostics",
        "test_run_diagnostics",
        "release_flow_analysis",
    } and not has_any_value(
        technical_params,
        execution_parameters,
        RUN_REFERENCE_KEYS | SOURCE_CONTROL_KEYS | ARTIFACT_REFERENCE_KEYS,
    ):
        missing_fields.append("technical_params.execution_parameters.run_or_release_reference")

    if ci_cd_scenario in {"job_status_analysis", "build_failure_diagnostics", "test_run_diagnostics"}:
        if not has_pipeline_log_context(
            technical_params,
            execution_parameters,
            agent_input.previous_step_outputs,
        ):
            missing_fields.append("technical_params.execution_parameters.pipeline_logs")

    if ci_cd_scenario == "ci_cd_config_change" and not has_any_value(
        technical_params,
        execution_parameters,
        VALIDATION_CONFIG_KEYS,
    ):
        missing_fields.append("technical_params.execution_parameters.config_changes")

    return deduplicate_texts(missing_fields)


def infer_ci_cd_scenario(agent_input: AgentExecutionInput) -> str:
    technical_params = agent_input.technical_params
    execution_parameters = dict(technical_params.get("execution_parameters") or {})
    operation_type = str(technical_params.get("operation_type") or "").strip().lower()
    task_type = agent_input.task_type

    if task_type == AgentTaskType.PIPELINE_PROCEDURE:
        if has_any_value(technical_params, execution_parameters, {"config_changes", "config_diff"}):
            return "ci_cd_config_change"
        if has_any_value(
            technical_params,
            execution_parameters,
            {"release_version", "tag", "artifact", "artifact_name", "image", "image_tag"},
        ):
            return "release_flow_analysis"
        return "pipeline_definition_analysis"

    if operation_type == "build":
        return "build_failure_diagnostics"
    if operation_type == "test":
        return "test_run_diagnostics"
    if operation_type == "release":
        return "release_flow_analysis"
    if operation_type == "configure":
        return "ci_cd_config_change"
    if operation_type == "pipeline":
        if has_any_value(technical_params, execution_parameters, {"run_id", "job_id", "job_name"}):
            return "job_status_analysis"
        if has_any_value(technical_params, execution_parameters, {"config_changes", "config_diff"}):
            return "ci_cd_config_change"
        return "pipeline_definition_analysis"
    if task_type == AgentTaskType.DIAGNOSTIC_PLAN:
        return "job_status_analysis"
    return "pipeline_definition_analysis"


def build_blocked_ci_cd_output(
    agent_input: AgentExecutionInput,
    missing_context: list[str],
) -> AgentExecutionOutput:
    audit_logger = SpecialistExecutionAuditLogger(
        owner_agent="CI_CD_Agent",
        request_id=agent_input.context.request_id,
        step_id=agent_input.step_id,
        user_id=agent_input.context.user_id,
    )
    audit_logger.record_input_received(agent_input.model_dump(mode="json"))
    audit_logger.record_decision(
        summary="CI/CD analysis blocked because required repository, pipeline, or run context is missing.",
        decision_type="missing_context_detected",
        payload={
            "missing_context": missing_context,
            "ci_cd_scenario": infer_ci_cd_scenario(agent_input),
        },
        status=AgentExecutionStatus.BLOCKED.value,
    )
    findings = ["Missing required CI/CD context: " + ", ".join(missing_context) + "."]
    output = AgentExecutionOutput(
        result={
            "focus": "ci_cd",
            "summary": "CI_CD_Agent is blocked by missing CI/CD context.",
            "findings": findings,
            "proposed_actions": [],
            "risks": [
                "CI/CD analysis cannot continue safely until repository, pipeline, logs, and execution references are provided."
            ],
            "artifacts": [],
        },
        logs=findings,
        status=AgentExecutionStatus.BLOCKED,
        analysis_details=[
            {
                "category": "ci_cd",
                "summary": "CI/CD step blocked before agent execution.",
                "details": {
                    "missing_context": missing_context,
                    "ci_cd_scenario": infer_ci_cd_scenario(agent_input),
                    "task_type": agent_input.task_type.value,
                    "service_name": agent_input.context.service_name,
                    "target_environment": agent_input.target_environment.value,
                },
            }
        ],
        warnings=["CI_CD_Agent skipped execution because required inputs are missing."],
    )
    return attach_execution_details(output=output, audit_logger=audit_logger)


def build_pipeline_log_context(
    technical_params: dict[str, Any],
    execution_parameters: dict[str, Any],
    previous_step_outputs: dict[str, Any],
) -> dict[str, Any]:
    current_logs = collect_matching_values(
        technical_params,
        execution_parameters,
        LOG_REFERENCE_KEYS,
    )
    dependency_logs = collect_dependency_log_references(previous_step_outputs)
    return {
        "current_step_inputs": current_logs,
        "dependency_references": dependency_logs,
        "available": bool(current_logs or dependency_logs),
    }


def collect_dependency_log_references(
    previous_step_outputs: dict[str, Any],
) -> dict[str, Any]:
    dependency_references: dict[str, Any] = {}
    for step_id, raw_output in previous_step_outputs.items():
        if not isinstance(raw_output, dict):
            continue
        result = raw_output.get("result")
        if isinstance(result, dict):
            artifacts = result.get("artifacts")
            if artifacts:
                dependency_references[step_id] = {"artifacts": artifacts}
        logs = raw_output.get("logs")
        if logs:
            dependency_references.setdefault(step_id, {})["logs"] = logs
    return dependency_references


def infer_validation_scope(
    technical_params: dict[str, Any],
    execution_parameters: dict[str, Any],
) -> list[str]:
    scope: list[str] = []
    if has_any_value(technical_params, execution_parameters, {"trigger_conditions", "workflow_file"}):
        scope.append("trigger_configuration")
    if has_any_value(technical_params, execution_parameters, {"jobs", "stages", "matrix"}):
        scope.append("job_and_stage_structure")
    if has_any_value(technical_params, execution_parameters, {"quality_gates", "test_report_summary"}):
        scope.append("quality_gates")
    if has_any_value(technical_params, execution_parameters, {"artifact", "artifact_name", "artifact_uri"}):
        scope.append("artifact_flow")
    if has_any_value(technical_params, execution_parameters, {"secrets_scope", "permissions_scope"}):
        scope.append("permissions_and_secrets")
    if has_any_value(technical_params, execution_parameters, {"release_version", "tag", "image_tag"}):
        scope.append("release_controls")
    if not scope:
        scope.append("pipeline_execution_path")
    return deduplicate_texts(scope)


def collect_matching_values(
    technical_params: dict[str, Any],
    execution_parameters: dict[str, Any],
    keys: set[str],
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key in sorted(keys):
        if has_value(technical_params.get(key)):
            values[key] = technical_params[key]
            continue
        if has_value(execution_parameters.get(key)):
            values[key] = execution_parameters[key]
    return values


def has_pipeline_log_context(
    technical_params: dict[str, Any],
    execution_parameters: dict[str, Any],
    previous_step_outputs: dict[str, Any],
) -> bool:
    if has_any_value(technical_params, execution_parameters, LOG_REFERENCE_KEYS):
        return True
    return bool(collect_dependency_log_references(previous_step_outputs))


def has_any_value(
    technical_params: dict[str, Any],
    execution_parameters: dict[str, Any],
    keys: set[str],
) -> bool:
    return any(
        has_value(technical_params.get(key)) or has_value(execution_parameters.get(key))
        for key in keys
    )


def has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def requires_execution_approval(recommended_actions: Sequence[Any]) -> bool:
    for action in recommended_actions:
        action_type = str(getattr(action, "action_type", "")).strip().lower()
        if action_type in EXECUTION_ONLY_ACTION_TYPES:
            return True
    return False


def deduplicate_texts(values: list[str]) -> list[str]:
    normalized_values: list[str] = []
    seen_values: set[str] = set()
    for value in values:
        normalized_value = value.strip()
        if not normalized_value or normalized_value in seen_values:
            continue
        seen_values.add(normalized_value)
        normalized_values.append(normalized_value)
    return normalized_values


def describe_tool(tool: ToolDefinition) -> str:
    return getattr(tool, "name", None) or str(tool)
