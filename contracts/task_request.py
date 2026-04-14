from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, computed_field, model_validator

from utils.task_request_parser import build_standardized_work_item


class RequestSource(str, Enum):
    JIRA = "jira"
    CHAT = "chat"
    API = "api"


class TargetEnvironment(str, Enum):
    DEV = "dev"
    STAGE = "stage"
    PROD = "prod"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class InputStatus(str, Enum):
    READY_FOR_PLANNING = "ready_for_planning"
    NEEDS_CLARIFICATION = "needs_clarification"


class ClarificationItem(BaseModel):
    field_name: str
    reason: str


class OperationType(str, Enum):
    DEPLOY = "deploy"
    ROLLBACK = "rollback"
    RESTART = "restart"
    SCALE = "scale"
    CONFIGURE = "configure"
    DIAGNOSE = "diagnose"
    PIPELINE = "pipeline"
    BUILD = "build"
    TEST = "test"
    RELEASE = "release"


class TaskParams(BaseModel):
    target_environment: TargetEnvironment | None = None
    priority: TaskPriority | None = None
    ticket_id: str | None = None
    conversation_id: str | None = None
    execution_options: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_blank_values(self) -> "TaskParams":
        self.ticket_id = normalize_optional_text(self.ticket_id)
        self.conversation_id = normalize_optional_text(self.conversation_id)
        return self


class TaskRequest(BaseModel):
    request_id: str
    source: RequestSource
    user_id: str
    user_request: str
    params: TaskParams = Field(default_factory=TaskParams)

    @model_validator(mode="before")
    @classmethod
    def map_legacy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        normalized_data = dict(data)
        if "user_request" not in normalized_data and "task_description" in normalized_data:
            normalized_data["user_request"] = normalized_data["task_description"]
        if "params" not in normalized_data and "parameters" in normalized_data:
            context = normalized_data.get("context", {})
            legacy_parameters = normalized_data.get("parameters", {})
            normalized_data["params"] = {
                "target_environment": context.get("environment"),
                "priority": context.get("priority"),
                "ticket_id": context.get("ticket_id"),
                "conversation_id": context.get("conversation_id"),
                "execution_options": legacy_parameters,
            }
        return normalized_data

    @model_validator(mode="after")
    def normalize_text_fields(self) -> "TaskRequest":
        self.request_id = self.request_id.strip()
        self.user_id = self.user_id.strip()
        self.user_request = self.user_request.strip()
        return self

    @computed_field
    @property
    def standardized_work_item(self) -> "StandardizedWorkItem":
        parsed_work_item = build_standardized_work_item(
            user_request=self.user_request,
            execution_options=self.params.execution_options,
            declared_environment=enum_value_or_none(self.params.target_environment),
        )
        return StandardizedWorkItem.model_validate(parsed_work_item)

    @computed_field
    @property
    def clarification_items(self) -> list[ClarificationItem]:
        missing_fields: list[ClarificationItem] = []

        if not self.request_id:
            missing_fields.append(
                ClarificationItem(
                    field_name="request_id",
                    reason="Identyfikator zgłoszenia jest wymagany do śledzenia i audytu.",
                )
            )

        if not self.user_id:
            missing_fields.append(
                ClarificationItem(
                    field_name="user_id",
                    reason="Identyfikator użytkownika jest wymagany do audytu zgłoszenia.",
                )
            )

        if not self.user_request:
            missing_fields.append(
                ClarificationItem(
                    field_name="user_request",
                    reason="Brak opisu zgłoszenia uniemożliwia planowanie workflow.",
                )
            )

        if self.standardized_work_item.target_environment is None:
            missing_fields.append(
                ClarificationItem(
                    field_name="standardized_work_item.target_environment",
                    reason="Środowisko docelowe musi zostać wskazane w parametrach lub treści zgłoszenia.",
                )
            )

        if self.params.priority is None:
            missing_fields.append(
                ClarificationItem(
                    field_name="params.priority",
                    reason="Priorytet jest wymagany do klasyfikacji zgłoszenia.",
                )
            )

        if self.standardized_work_item.service_name is None:
            missing_fields.append(
                ClarificationItem(
                    field_name="standardized_work_item.service_name",
                    reason="Nazwa usługi musi zostać wskazana przed planowaniem workflow.",
                )
            )

        if self.standardized_work_item.operation_type is None:
            missing_fields.append(
                ClarificationItem(
                    field_name="standardized_work_item.operation_type",
                    reason="Typ operacji musi zostać wskazany lub wynikać z treści zgłoszenia.",
                )
            )

        if self.source == RequestSource.JIRA and not self.params.ticket_id:
            missing_fields.append(
                ClarificationItem(
                    field_name="params.ticket_id",
                    reason="Zgłoszenie z Jira musi zawierać identyfikator ticketa.",
                )
            )

        if self.source == RequestSource.CHAT and not self.params.conversation_id:
            missing_fields.append(
                ClarificationItem(
                    field_name="params.conversation_id",
                    reason="Zgłoszenie z chatu musi zawierać identyfikator rozmowy.",
                )
            )

        return deduplicate_clarification_items(missing_fields)

    @computed_field
    @property
    def input_status(self) -> InputStatus:
        if self.clarification_items:
            return InputStatus.NEEDS_CLARIFICATION
        return InputStatus.READY_FOR_PLANNING

    def to_prompt(self) -> str:
        return (
            "Prepare a Supervisor planning response for the DevOps task below.\n\n"
            f"request_id: {self.request_id}\n"
            f"source: {self.source.value}\n"
            f"user_id: {self.user_id}\n"
            f"user_request: {self.user_request}\n"
            f"input_status: {self.input_status.value}\n"
            f"standardized_work_item.service_name: {self.standardized_work_item.service_name}\n"
            "standardized_work_item.target_environment: "
            f"{enum_value_or_none(self.standardized_work_item.target_environment)}\n"
            "standardized_work_item.operation_type: "
            f"{enum_value_or_none(self.standardized_work_item.operation_type)}\n"
            "standardized_work_item.execution_parameters: "
            f"{self.standardized_work_item.execution_parameters}\n"
            f"standardized_work_item.constraints: {self.standardized_work_item.constraints}\n"
            f"params.target_environment: {enum_value_or_none(self.params.target_environment)}\n"
            f"params.priority: {enum_value_or_none(self.params.priority)}\n"
            f"params.ticket_id: {self.params.ticket_id}\n"
            f"params.conversation_id: {self.params.conversation_id}\n"
            f"params.execution_options: {self.params.execution_options}\n\n"
            "Return only valid JSON with this structure:\n"
            "{\n"
            '  "plan": [\n'
            "    {\n"
            '      "step_id": "STEP-1",\n'
            '      "owner_agent": "DeploymentAgent|InfraAgent|CI_CD_Agent|Risk/Policy Agent|Human Review Interface",\n'
            '      "task_type": "deployment_analysis|infrastructure_analysis|ci_cd_analysis|service_rollout|environment_change|pipeline_procedure|diagnostic_plan|risk_policy_review|human_approval|execution_handoff|final_report",\n'
            '      "task_description": "string",\n'
            '      "step_order": 1,\n'
            '      "depends_on": ["STEP-0"],\n'
            '      "required_input_context": {},\n'
            '      "expected_result": "string",\n'
            '      "status": "planned|waiting_for_approval|blocked",\n'
            '      "risk_flags": ["string"],\n'
            '      "requires_user_approval": false\n'
            "    }\n"
            "  ],\n"
            '  "confidence": 0.0,\n'
            '  "risk_flags": ["string"],\n'
            '  "requires_user_approval": false\n'
            "}\n"
        )


class StandardizedWorkItem(BaseModel):
    service_name: str | None = None
    target_environment: TargetEnvironment | None = None
    operation_type: OperationType | None = None
    execution_parameters: dict[str, Any] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped_value = value.strip()
    return stripped_value or None


def enum_value_or_none(value: Enum | None) -> str | None:
    if value is None:
        return None
    return str(value.value)


def deduplicate_clarification_items(
    clarification_items: list[ClarificationItem],
) -> list[ClarificationItem]:
    unique_items: list[ClarificationItem] = []
    seen_fields: set[str] = set()

    for item in clarification_items:
        if item.field_name in seen_fields:
            continue
        seen_fields.add(item.field_name)
        unique_items.append(item)

    return unique_items
