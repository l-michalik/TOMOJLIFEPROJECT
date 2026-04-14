from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from contracts.task_request import RequestSource, TargetEnvironment, TaskPriority, TaskRequest


class AgentTaskType(str, Enum):
    DEPLOYMENT_ANALYSIS = "deployment_analysis"
    INFRASTRUCTURE_ANALYSIS = "infrastructure_analysis"
    CI_CD_ANALYSIS = "ci_cd_analysis"
    SERVICE_ROLLOUT = "service_rollout"
    ENVIRONMENT_CHANGE = "environment_change"
    PIPELINE_PROCEDURE = "pipeline_procedure"
    DIAGNOSTIC_PLAN = "diagnostic_plan"
    RISK_POLICY_REVIEW = "risk_policy_review"
    HUMAN_APPROVAL = "human_approval"
    EXECUTION_HANDOFF = "execution_handoff"
    FINAL_REPORT = "final_report"


class AgentExecutionContext(BaseModel):
    request_id: str
    source: RequestSource
    user_id: str
    user_request: str
    priority: TaskPriority
    service_name: str

    @model_validator(mode="after")
    def normalize_text_fields(self) -> "AgentExecutionContext":
        self.request_id = self.request_id.strip()
        self.user_id = self.user_id.strip()
        self.user_request = self.user_request.strip()
        self.service_name = self.service_name.strip()
        return self


class AgentExecutionInput(BaseModel):
    instruction: str
    context: AgentExecutionContext
    step_id: str
    owner_agent: str
    task_type: AgentTaskType
    target_environment: TargetEnvironment
    technical_params: dict[str, Any] = Field(default_factory=dict)
    execution_constraints: list[str] = Field(default_factory=list)
    previous_step_outputs: dict[str, Any] = Field(default_factory=dict)
    safety_flags: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    expected_output_json_format: dict[str, Any] = Field(default_factory=dict)
    expected_result: str
    result_handoff_condition: str

    @model_validator(mode="after")
    def validate_contract_consistency(self) -> "AgentExecutionInput":
        self.instruction = self.instruction.strip()
        self.step_id = self.step_id.strip()
        self.owner_agent = self.owner_agent.strip()
        self.expected_result = self.expected_result.strip()
        self.result_handoff_condition = self.result_handoff_condition.strip()
        self.execution_constraints = normalize_text_list(self.execution_constraints)
        self.safety_flags = normalize_text_list(self.safety_flags)

        if not self.instruction:
            raise ValueError("instruction must not be blank")
        if not self.step_id:
            raise ValueError("step_id must not be blank")
        if not self.owner_agent:
            raise ValueError("owner_agent must not be blank")
        if not self.expected_result:
            raise ValueError("expected_result must not be blank")
        if not self.result_handoff_condition:
            raise ValueError("result_handoff_condition must not be blank")
        if not self.technical_params:
            raise ValueError("technical_params must contain the step execution parameters")
        if not self.expected_output_json_format:
            raise ValueError(
                "expected_output_json_format must define the specialist response schema"
            )

        required_param_values = {
            "service_name": self.context.service_name,
            "target_environment": self.target_environment.value,
            "task_type": self.task_type.value,
        }
        for key, expected_value in required_param_values.items():
            actual_value = self.technical_params.get(key)
            if actual_value != expected_value:
                raise ValueError(
                    f"technical_params.{key} must match the normalized contract value"
                )

        return self

    @classmethod
    def from_workflow_step(
        cls,
        *,
        step_id: str,
        owner_agent: str,
        task_type: AgentTaskType,
        instruction: str,
        target_environment: TargetEnvironment,
        technical_params: dict[str, Any],
        execution_constraints: list[str],
        previous_step_outputs: dict[str, Any],
        safety_flags: list[str],
        depends_on: list[str],
        expected_output_json_format: dict[str, Any],
        expected_result: str,
        result_handoff_condition: str,
        task_request: TaskRequest,
    ) -> "AgentExecutionInput":
        work_item = task_request.standardized_work_item
        normalized_technical_params = dict(technical_params)
        normalized_technical_params["service_name"] = work_item.service_name
        normalized_technical_params["target_environment"] = target_environment.value
        normalized_technical_params["task_type"] = task_type.value
        if work_item.operation_type is not None:
            normalized_technical_params.setdefault(
                "operation_type",
                work_item.operation_type.value,
            )

        return cls(
            instruction=instruction,
            context=AgentExecutionContext(
                request_id=task_request.request_id,
                source=task_request.source,
                user_id=task_request.user_id,
                user_request=task_request.user_request,
                priority=task_request.params.priority,
                service_name=work_item.service_name,
            ),
            step_id=step_id,
            owner_agent=owner_agent,
            task_type=task_type,
            target_environment=target_environment,
            technical_params=normalized_technical_params,
            execution_constraints=execution_constraints,
            previous_step_outputs=previous_step_outputs,
            safety_flags=safety_flags,
            depends_on=depends_on,
            expected_output_json_format=expected_output_json_format,
            expected_result=expected_result,
            result_handoff_condition=result_handoff_condition,
        )


def normalize_text_list(values: list[str]) -> list[str]:
    normalized_values: list[str] = []
    seen_values: set[str] = set()

    for value in values:
        normalized_value = value.strip()
        if not normalized_value or normalized_value in seen_values:
            continue
        seen_values.add(normalized_value)
        normalized_values.append(normalized_value)

    return normalized_values
