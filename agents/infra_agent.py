from __future__ import annotations

import json
from typing import Any, Sequence

from deepagents import create_deep_agent

from agents.specialist_base import BaseSpecialistAgent
from contracts.agent_input import AgentExecutionInput, AgentTaskType
from contracts.agent_output import AgentExecutionOutput, AgentExecutionStatus
from settings.supervisor import load_prompt
from utils.specialist_execution_logging import (
    SpecialistExecutionAuditLogger,
    attach_execution_details,
)

ToolDefinition = Any

RUNTIME_CONFIGURATION_KEYS = {
    "config_key",
    "config_keys",
    "config_scope",
    "config_value",
    "env_var",
    "env_vars",
    "secret_name",
    "secret_names",
    "secret_scope",
    "secret_path",
    "runtime_config",
}
RESOURCE_TARGET_KEYS = {
    "resource_id",
    "resource_ids",
    "resource_name",
    "resource_names",
    "cluster",
    "cluster_name",
    "namespace",
    "region",
    "vpc",
    "subnet",
    "dns_zone",
    "storage_class",
    "iam_principal",
}
RESOURCE_CHANGE_KEYS = RESOURCE_TARGET_KEYS | {
    "replica_count",
    "desired_capacity",
    "desired_state",
}
IGNORED_EXECUTION_PARAMETER_KEYS = {
    "service_name",
    "target_environment",
    "operation_type",
    "constraints",
}


class InfraAgent(BaseSpecialistAgent):
    def __init__(
        self,
        *,
        model: str,
        tools: Sequence[ToolDefinition] | None = None,
        deep_agent_factory: Any | None = None,
    ) -> None:
        super().__init__(
            model=model,
            owner_agent="InfraAgent",
            system_prompt=load_prompt("infra_agent.md"),
            agent_name="infra-agent",
            tools=tools,
            request_log_summary="Analyze infrastructure dependencies and required changes.",
            response_log_summary="Infrastructure analysis result received.",
            deep_agent_factory=deep_agent_factory or create_deep_agent,
        )

    def run(self, payload: AgentExecutionInput | dict[str, Any]) -> AgentExecutionOutput:
        try:
            agent_input = AgentExecutionInput.model_validate(payload)
        except Exception as exc:
            audit_logger = SpecialistExecutionAuditLogger(
                owner_agent="InfraAgent",
                input_snapshot=payload,
            )
            audit_logger.record_error(
                summary="InfraAgent input contract validation failed.",
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

        missing_context = identify_missing_infrastructure_context(agent_input)
        if missing_context:
            return build_blocked_infrastructure_output(agent_input, missing_context)
        return super().run(agent_input)

    def build_additional_prompt_sections(
        self,
        agent_input: AgentExecutionInput,
    ) -> list[str]:
        execution_parameters = dict(
            agent_input.technical_params.get("execution_parameters") or {}
        )
        scenario = infer_infrastructure_scenario(agent_input)
        tool_names = [describe_tool(tool) for tool in self.tools]
        return [
            "Infrastructure context summary:\n"
            + json.dumps(
                {
                    "service_name": agent_input.context.service_name,
                    "target_environment": agent_input.target_environment.value,
                    "task_type": agent_input.task_type.value,
                    "operation_type": agent_input.technical_params.get("operation_type"),
                    "infrastructure_scenario": scenario,
                    "affected_layers": infer_infrastructure_layers(
                        agent_input.technical_params,
                        execution_parameters,
                    ),
                    "execution_parameters": execution_parameters,
                    "depends_on": list(agent_input.depends_on),
                    "previous_step_output_ids": sorted(
                        agent_input.previous_step_outputs.keys()
                    ),
                },
                ensure_ascii=True,
                indent=2,
            ),
            "Infrastructure tool policy:\n"
            + json.dumps(
                {
                    "allowed_tools": tool_names,
                    "tool_usage_mode": (
                        "inspection_validation_and_planning_only"
                        if tool_names
                        else "analysis_only"
                    ),
                },
                ensure_ascii=True,
                indent=2,
            ),
        ]


def identify_missing_infrastructure_context(
    agent_input: AgentExecutionInput,
) -> list[str]:
    missing_fields: list[str] = []
    technical_params = agent_input.technical_params
    execution_parameters = dict(technical_params.get("execution_parameters") or {})
    operation_type = str(technical_params.get("operation_type") or "").strip()
    scenario = infer_infrastructure_scenario(agent_input)

    if not operation_type:
        missing_fields.append("technical_params.operation_type")

    if scenario == "resource_change" and not has_any_key(
        technical_params,
        execution_parameters,
        RESOURCE_CHANGE_KEYS,
    ):
        missing_fields.append("technical_params.execution_parameters.resource_target")

    if scenario == "environment_config_change" and not has_configuration_target(
        technical_params,
        execution_parameters,
    ):
        missing_fields.append("technical_params.execution_parameters.configuration_scope")

    return missing_fields


def infer_infrastructure_scenario(agent_input: AgentExecutionInput) -> str:
    operation_type = str(agent_input.technical_params.get("operation_type") or "").strip()

    if agent_input.task_type == AgentTaskType.DIAGNOSTIC_PLAN:
        return "environment_diagnostics"
    if agent_input.task_type == AgentTaskType.ENVIRONMENT_CHANGE:
        if operation_type == "scale":
            return "resource_change"
        if operation_type == "configure":
            return "environment_config_change"
        return "other_infrastructure"
    if operation_type in {"deploy", "rollback", "restart", "release"}:
        return "platform_prerequisite"
    if operation_type == "diagnose":
        return "environment_diagnostics"
    if operation_type == "scale":
        return "resource_change"
    if operation_type == "configure":
        return "environment_config_change"
    return "other_infrastructure"


def infer_infrastructure_layers(
    technical_params: dict[str, Any],
    execution_parameters: dict[str, Any],
) -> list[str]:
    layers: list[str] = []
    if has_any_key(technical_params, execution_parameters, {"cluster", "namespace"}):
        layers.append("platform")
        layers.append("compute")
    if has_any_key(technical_params, execution_parameters, {"vpc", "subnet", "dns_zone"}):
        layers.append("network")
    if has_any_key(
        technical_params,
        execution_parameters,
        {"iam_principal", "role", "roles", "permission", "permissions"},
    ):
        layers.append("iam")
    if has_any_key(technical_params, execution_parameters, RUNTIME_CONFIGURATION_KEYS):
        layers.append("secret/config")
    if has_any_key(
        technical_params,
        execution_parameters,
        {"storage_class", "bucket", "volume", "disk", "mount_path"},
    ):
        layers.append("storage")
    if not layers:
        layers.append("shared_environment_dependencies")
    return deduplicate_texts(layers)


def has_configuration_target(
    technical_params: dict[str, Any],
    execution_parameters: dict[str, Any],
) -> bool:
    if has_any_key(technical_params, execution_parameters, RUNTIME_CONFIGURATION_KEYS):
        return True
    meaningful_execution_keys = {
        key
        for key in execution_parameters
        if key not in IGNORED_EXECUTION_PARAMETER_KEYS
    }
    return bool(meaningful_execution_keys)


def has_any_key(
    technical_params: dict[str, Any],
    execution_parameters: dict[str, Any],
    keys: set[str],
) -> bool:
    for key in keys:
        if has_value(technical_params.get(key)) or has_value(execution_parameters.get(key)):
            return True
    return False


def has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def deduplicate_texts(values: list[str]) -> list[str]:
    normalized_values: list[str] = []
    seen_values: set[str] = set()
    for value in values:
        if value in seen_values:
            continue
        seen_values.add(value)
        normalized_values.append(value)
    return normalized_values


def build_blocked_infrastructure_output(
    agent_input: AgentExecutionInput,
    missing_context: list[str],
) -> AgentExecutionOutput:
    scenario = infer_infrastructure_scenario(agent_input)
    audit_logger = SpecialistExecutionAuditLogger(
        owner_agent="InfraAgent",
        request_id=agent_input.context.request_id,
        step_id=agent_input.step_id,
        user_id=agent_input.context.user_id,
    )
    audit_logger.record_input_received(agent_input.model_dump(mode="json"))
    audit_logger.record_decision(
        summary="Infrastructure analysis blocked because required infrastructure context is missing.",
        decision_type="missing_context_detected",
        payload={
            "missing_context": missing_context,
            "infrastructure_scenario": scenario,
        },
        status=AgentExecutionStatus.BLOCKED.value,
    )
    findings = [
        "Missing required infrastructure context: " + ", ".join(missing_context) + "."
    ]
    output = AgentExecutionOutput(
        result={
            "focus": "infrastructure",
            "infrastructure_scenario": scenario,
            "summary": "InfraAgent is blocked by missing infrastructure context.",
            "findings": findings,
            "required_inputs": missing_context,
            "proposed_actions": [],
            "risks": [
                "Infrastructure planning cannot continue safely until the missing inputs are provided."
            ],
            "artifacts": [],
        },
        logs=findings,
        status=AgentExecutionStatus.BLOCKED,
        analysis_details=[
            {
                "category": "infrastructure",
                "summary": "Infrastructure step blocked before agent execution.",
                "details": {
                    "missing_context": missing_context,
                    "infrastructure_scenario": scenario,
                    "task_type": agent_input.task_type.value,
                    "service_name": agent_input.context.service_name,
                    "target_environment": agent_input.target_environment.value,
                },
            }
        ],
        warnings=["InfraAgent skipped execution because required inputs are missing."],
    )
    return attach_execution_details(output=output, audit_logger=audit_logger)


def describe_tool(tool: ToolDefinition) -> str:
    return getattr(tool, "name", None) or str(tool)
