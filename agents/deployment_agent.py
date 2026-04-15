from __future__ import annotations

import json
from typing import Any, Sequence

from deepagents import create_deep_agent

from contracts.agent_input import AgentExecutionInput, AgentTaskType
from contracts.agent_output import AgentExecutionOutput, AgentExecutionStatus
from agents.specialist_base import BaseSpecialistAgent
from settings.supervisor import load_prompt

ToolDefinition = Any

PARTIAL_DEPLOYMENT_STATUSES = {"partial", "partial_execution", "partially_completed"}
DEPLOYMENT_REFERENCE_KEYS = (
    "release_version",
    "version",
    "artifact",
    "artifact_uri",
    "artifact_name",
    "image",
    "image_tag",
    "tag",
)


class DeploymentAgent(BaseSpecialistAgent):
    def __init__(
        self,
        *,
        model: str,
        tools: Sequence[ToolDefinition] | None = None,
        deep_agent_factory: Any | None = None,
    ) -> None:
        super().__init__(
            model=model,
            owner_agent="DeploymentAgent",
            system_prompt=load_prompt("deployment_agent.md"),
            agent_name="deployment-agent",
            tools=tools,
            request_log_summary="Analyze the deployment plan and release actions.",
            response_log_summary="Deployment analysis result received.",
            deep_agent_factory=deep_agent_factory or create_deep_agent,
        )

    def run(self, payload: AgentExecutionInput | dict[str, Any]) -> AgentExecutionOutput:
        try:
            agent_input = AgentExecutionInput.model_validate(payload)
        except Exception as exc:
            return self.build_failed_output(
                code="invalid_agent_input",
                message="Specialist agent input contract validation failed.",
                details={"error": str(exc)},
            )

        missing_context = identify_missing_deployment_context(agent_input)
        if missing_context:
            return build_blocked_deployment_output(agent_input, missing_context)
        return super().run(agent_input)

    def build_additional_prompt_sections(
        self,
        agent_input: AgentExecutionInput,
    ) -> list[str]:
        deployment_context = {
            "service_name": agent_input.context.service_name,
            "target_environment": agent_input.target_environment.value,
            "task_type": agent_input.task_type.value,
            "operation_type": agent_input.technical_params.get("operation_type"),
            "execution_parameters": dict(
                agent_input.technical_params.get("execution_parameters") or {}
            ),
            "safety_flags": list(agent_input.safety_flags),
            "depends_on": list(agent_input.depends_on),
            "previous_step_output_ids": sorted(agent_input.previous_step_outputs.keys()),
        }
        tool_names = [describe_tool(tool) for tool in self.tools]
        return [
            "Deployment context summary:\n"
            + json.dumps(deployment_context, ensure_ascii=True, indent=2),
            "Deployment tool policy:\n"
            + json.dumps(
                {
                    "allowed_tools": tool_names,
                    "tool_usage_mode": (
                        "analysis_and_read_only_execution_support"
                        if tool_names
                        else "analysis_only"
                    ),
                },
                ensure_ascii=True,
                indent=2,
            ),
        ]

    def parse_output(self, raw_text: str) -> AgentExecutionOutput:
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            return super().parse_output(raw_text)

        normalized_payload = normalize_partial_deployment_payload(payload)
        try:
            return AgentExecutionOutput.model_validate(normalized_payload)
        except Exception as exc:
            return self.build_failed_output(
                code="invalid_agent_output",
                message="Specialist agent returned JSON that does not match the output contract.",
                details={"error": str(exc)},
            )


def identify_missing_deployment_context(agent_input: AgentExecutionInput) -> list[str]:
    missing_fields: list[str] = []
    technical_params = agent_input.technical_params
    operation_type = str(technical_params.get("operation_type") or "").strip()
    execution_parameters = dict(technical_params.get("execution_parameters") or {})

    if not operation_type:
        missing_fields.append("technical_params.operation_type")

    if agent_input.task_type == AgentTaskType.SERVICE_ROLLOUT and not agent_input.depends_on:
        missing_fields.append("depends_on")

    if operation_type in {"deploy", "rollback"} and not has_release_reference(
        technical_params,
        execution_parameters,
    ):
        missing_fields.append(
            "technical_params.execution_parameters.release_reference"
        )

    return missing_fields


def has_release_reference(
    technical_params: dict[str, Any],
    execution_parameters: dict[str, Any],
) -> bool:
    for key in DEPLOYMENT_REFERENCE_KEYS:
        if has_text_value(technical_params.get(key)) or has_text_value(
            execution_parameters.get(key)
        ):
            return True
    return False


def has_text_value(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def build_blocked_deployment_output(
    agent_input: AgentExecutionInput,
    missing_context: list[str],
) -> AgentExecutionOutput:
    findings = [
        "Missing required deployment context: " + ", ".join(missing_context) + "."
    ]
    return AgentExecutionOutput(
        result={
            "focus": "deployment",
            "summary": "DeploymentAgent is blocked by missing deployment context.",
            "findings": findings,
            "proposed_actions": [],
            "risks": [
                "Deployment planning cannot continue safely until the missing inputs are provided."
            ],
            "artifacts": [],
        },
        logs=findings,
        status=AgentExecutionStatus.BLOCKED,
        analysis_details=[
            {
                "category": "deployment",
                "summary": "Deployment step blocked before agent execution.",
                "details": {
                    "missing_context": missing_context,
                    "task_type": agent_input.task_type.value,
                    "service_name": agent_input.context.service_name,
                    "target_environment": agent_input.target_environment.value,
                },
            }
        ],
        warnings=["DeploymentAgent skipped execution because required inputs are missing."],
    )


def normalize_partial_deployment_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload

    status = str(payload.get("status") or "").strip().lower()
    if status not in PARTIAL_DEPLOYMENT_STATUSES:
        return payload

    normalized_payload = dict(payload)
    normalized_payload["status"] = AgentExecutionStatus.BLOCKED.value

    logs = list(normalized_payload.get("logs") or [])
    logs.append("DeploymentAgent normalized partial deployment output to blocked.")
    normalized_payload["logs"] = logs

    warnings = list(normalized_payload.get("warnings") or [])
    warnings.append(
        "Partial deployment output requires follow-up before Supervisor can continue safely."
    )
    normalized_payload["warnings"] = warnings

    result = dict(normalized_payload.get("result") or {})
    result.setdefault(
        "summary",
        "Deployment analysis returned a partial result and requires follow-up.",
    )
    result.setdefault(
        "findings",
        ["Partial deployment output was returned and normalized to blocked."],
    )
    result.setdefault(
        "risks",
        ["Deployment state is incomplete and cannot be handed off for execution."],
    )
    normalized_payload["result"] = result
    return normalized_payload


def describe_tool(tool: ToolDefinition) -> str:
    return getattr(tool, "name", None) or str(tool)
