from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from contracts.agent_session_memory import AgentSessionMemory


class AgentExecutionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    WAITING_FOR_APPROVAL = "waiting_for_approval"


AGENT_EXECUTION_STATUS_WORKFLOW_MEANINGS: dict[AgentExecutionStatus, str] = {
    AgentExecutionStatus.COMPLETED: (
        "Step finished successfully and Supervisor may continue dependent workflow steps."
    ),
    AgentExecutionStatus.FAILED: (
        "Step failed technically or semantically and Supervisor should mark the step as failed."
    ),
    AgentExecutionStatus.BLOCKED: (
        "Step cannot continue because a dependency, policy, or required context is missing."
    ),
    AgentExecutionStatus.WAITING_FOR_APPROVAL: (
        "Step requires a human decision before the workflow can continue."
    ),
}


class AgentAnalysisDetail(BaseModel):
    category: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class AgentRecommendedAction(BaseModel):
    action_id: str
    action_type: str
    description: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AgentArtifactReference(BaseModel):
    name: str
    artifact_type: str
    uri: str | None = None
    description: str | None = None


class SupervisorFailureRecommendation(BaseModel):
    can_retry: bool = False
    recommended_action: str | None = None
    reason: str | None = None


class AgentTechnicalError(BaseModel):
    message: str
    code: str | None = None
    category: str | None = None
    supervisor_recommendation: SupervisorFailureRecommendation | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class SupervisorAggregationPayload(BaseModel):
    produced_action_ids: list[str] = Field(default_factory=list)
    blocked_action_ids: list[str] = Field(default_factory=list)
    approval_required_action_ids: list[str] = Field(default_factory=list)
    next_decision: str | None = None
    handoff_payload: dict[str, Any] = Field(default_factory=dict)


class AgentExecutionOutput(BaseModel):
    result: dict[str, Any] = Field(default_factory=dict)
    logs: list[str] = Field(default_factory=list)
    status: AgentExecutionStatus
    execution_details: dict[str, Any] = Field(default_factory=dict)
    analysis_details: list[AgentAnalysisDetail] = Field(default_factory=list)
    recommended_actions: list[AgentRecommendedAction] = Field(default_factory=list)
    artifacts: list[AgentArtifactReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    technical_errors: list[AgentTechnicalError] = Field(default_factory=list)
    supervisor_data: SupervisorAggregationPayload = Field(
        default_factory=SupervisorAggregationPayload
    )
    session_memory: AgentSessionMemory | None = None

    @model_validator(mode="before")
    @classmethod
    def map_legacy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        normalized_data = dict(data)
        result = normalized_result_payload(normalized_data.get("result"))
        normalized_data["result"] = result

        if "analysis_details" not in normalized_data:
            normalized_data["analysis_details"] = build_analysis_details_from_result(result)
        if "recommended_actions" not in normalized_data:
            normalized_data["recommended_actions"] = build_recommended_actions_from_result(
                result
            )
        if "artifacts" not in normalized_data:
            normalized_data["artifacts"] = build_artifacts_from_result(result)
        if "warnings" not in normalized_data:
            normalized_data["warnings"] = normalize_text_list(result.get("warnings", []))
        if "technical_errors" not in normalized_data:
            normalized_data["technical_errors"] = build_technical_errors_from_payload(
                normalized_data
            )
        if "supervisor_data" not in normalized_data:
            normalized_data["supervisor_data"] = build_supervisor_data_from_payload(
                result=result,
                recommended_actions=normalized_data.get("recommended_actions"),
            )

        return normalized_data

    @model_validator(mode="after")
    def sync_legacy_result_payload(self) -> "AgentExecutionOutput":
        self.logs = normalize_text_list(self.logs)
        self.warnings = normalize_text_list(self.warnings)

        if self.analysis_details and "analysis_details" not in self.result:
            self.result["analysis_details"] = [
                detail.model_dump(mode="json") for detail in self.analysis_details
            ]
        if self.recommended_actions and "proposed_actions" not in self.result:
            self.result["proposed_actions"] = [
                {
                    "action_id": action.action_id,
                    "action_type": action.action_type,
                    "description": action.description,
                    "details": action.details,
                }
                for action in self.recommended_actions
            ]
        if self.artifacts and "artifacts" not in self.result:
            self.result["artifacts"] = [artifact_reference_value(item) for item in self.artifacts]
        if self.warnings and "warnings" not in self.result:
            self.result["warnings"] = list(self.warnings)
        return self


def normalized_result_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return dict(payload)
    return {}


def build_analysis_details_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    analysis_details = result.get("analysis_details")
    if isinstance(analysis_details, list):
        return analysis_details

    summary = result.get("summary")
    findings = result.get("findings")
    if summary or findings:
        return [
            {
                "category": str(result.get("focus") or "analysis"),
                "summary": str(summary or "Analysis completed."),
                "details": {
                    "findings": findings if isinstance(findings, list) else [],
                },
            }
        ]
    return []


def build_recommended_actions_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    proposed_actions = result.get("proposed_actions")
    if not isinstance(proposed_actions, list):
        return []

    normalized_actions: list[dict[str, Any]] = []
    for index, raw_action in enumerate(proposed_actions, start=1):
        if not isinstance(raw_action, dict):
            continue
        normalized_actions.append(
            {
                "action_id": str(raw_action.get("action_id") or f"ACTION-{index}"),
                "action_type": str(raw_action.get("action_type") or "unknown"),
                "description": raw_action.get("description"),
                "details": dict(raw_action.get("details") or {}),
            }
        )
    return normalized_actions


def build_artifacts_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    raw_artifacts = result.get("artifacts")
    if not isinstance(raw_artifacts, list):
        return []

    normalized_artifacts: list[dict[str, Any]] = []
    for artifact in raw_artifacts:
        if isinstance(artifact, dict):
            normalized_artifacts.append(
                {
                    "name": str(artifact.get("name") or artifact.get("uri") or "artifact"),
                    "artifact_type": str(artifact.get("artifact_type") or "reference"),
                    "uri": artifact.get("uri"),
                    "description": artifact.get("description"),
                }
            )
            continue
        normalized_artifacts.append(
            {
                "name": str(artifact),
                "artifact_type": "reference",
                "uri": str(artifact),
                "description": None,
            }
        )
    return normalized_artifacts


def build_technical_errors_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("technical_errors"), list):
        return payload["technical_errors"]

    legacy_error = payload.get("error") or payload.get("error_details")
    if isinstance(legacy_error, dict):
        return [
            {
                "message": str(legacy_error.get("message") or "Specialist agent step failed."),
                "code": legacy_error.get("code"),
                "category": legacy_error.get("category"),
                "supervisor_recommendation": legacy_error.get(
                    "supervisor_recommendation"
                ),
                "details": {
                    key: value
                    for key, value in legacy_error.items()
                    if key
                    not in {
                        "message",
                        "code",
                        "category",
                        "supervisor_recommendation",
                    }
                },
            }
        ]
    if legacy_error:
        return [
            {
                "message": str(legacy_error),
                "code": None,
                "category": None,
                "supervisor_recommendation": None,
                "details": {},
            }
        ]
    return []


def build_supervisor_data_from_payload(
    result: dict[str, Any],
    recommended_actions: Any,
) -> dict[str, Any]:
    proposed_actions = normalize_recommended_actions(recommended_actions)
    if not proposed_actions:
        proposed_actions = build_recommended_actions_from_result(result)
    decisions = result.get("decisions")
    execution_handoff = result.get("execution_handoff")

    supervisor_data = {
        "produced_action_ids": [action["action_id"] for action in proposed_actions],
        "blocked_action_ids": [],
        "approval_required_action_ids": [],
        "next_decision": None,
        "handoff_payload": {},
    }

    if isinstance(decisions, list):
        supervisor_data["blocked_action_ids"] = [
            str(item.get("action_id"))
            for item in decisions
            if isinstance(item, dict) and not bool(item.get("allowed"))
        ]
        supervisor_data["approval_required_action_ids"] = [
            str(item.get("action_id"))
            for item in decisions
            if isinstance(item, dict)
            and bool(item.get("allowed"))
            and bool(
                item.get("requires_approval")
                if "requires_approval" in item
                else item.get("requiresApproval")
            )
        ]
        if supervisor_data["approval_required_action_ids"]:
            supervisor_data["next_decision"] = "await_user_approval"
        elif supervisor_data["blocked_action_ids"]:
            supervisor_data["next_decision"] = "review_blocked_steps"

    if isinstance(execution_handoff, dict):
        supervisor_data["handoff_payload"] = execution_handoff

    return supervisor_data


def normalize_recommended_actions(recommended_actions: Any) -> list[dict[str, Any]]:
    if not isinstance(recommended_actions, list):
        return []

    normalized_actions: list[dict[str, Any]] = []
    for index, raw_action in enumerate(recommended_actions, start=1):
        if isinstance(raw_action, AgentRecommendedAction):
            normalized_actions.append(raw_action.model_dump(mode="json"))
            continue
        if not isinstance(raw_action, dict):
            continue
        normalized_actions.append(
            {
                "action_id": str(raw_action.get("action_id") or f"ACTION-{index}"),
                "action_type": str(raw_action.get("action_type") or "unknown"),
                "description": raw_action.get("description"),
                "details": dict(raw_action.get("details") or {}),
            }
        )
    return normalized_actions


def build_agent_execution_output_format(
    expected_result_format: dict[str, Any],
) -> dict[str, Any]:
    return {
        "result": expected_result_format,
        "logs": ["string"],
        "status": "completed|failed|blocked|waiting_for_approval",
        "analysis_details": [
            {
                "category": "string",
                "summary": "string",
                "details": {},
            }
        ],
        "recommended_actions": [
            {
                "action_id": "string",
                "action_type": "string",
                "description": "string",
                "details": {},
            }
        ],
        "artifacts": [
            {
                "name": "string",
                "artifact_type": "string",
                "uri": "string",
                "description": "string",
            }
        ],
        "warnings": ["string"],
        "technical_errors": [
            {
                "message": "string",
                "code": "string",
                "category": "string",
                "supervisor_recommendation": {
                    "can_retry": False,
                    "recommended_action": "retry|escalate|mark_failed",
                    "reason": "string",
                },
                "details": {},
            }
        ],
        "supervisor_data": {
            "produced_action_ids": ["string"],
            "blocked_action_ids": ["string"],
            "approval_required_action_ids": ["string"],
            "next_decision": "string",
            "handoff_payload": {},
        },
        "session_memory": {
            "request_id": "string",
            "step_id": "string",
            "owner_agent": "string",
            "authority": {
                "authoritative_source": "supervisor_workflow_state",
                "scope": "single_step_execution",
                "is_source_of_truth": False,
                "usage_rule": "string",
            },
            "current_task_context": {},
            "recent_commands": [{"summary": "string", "source": "execution_details"}],
            "intermediate_results": [
                {
                    "source_step_id": "string",
                    "summary": "string",
                    "payload": {},
                }
            ],
            "environment_logs": ["string"],
            "technical_notes": {},
            "updated_at": "2026-04-15T10:00:00Z",
        },
    }


def artifact_reference_value(artifact: AgentArtifactReference) -> str:
    return artifact.uri or artifact.name


def normalize_text_list(values: list[Any]) -> list[str]:
    normalized_values: list[str] = []
    seen_values: set[str] = set()
    for value in values:
        normalized_value = str(value).strip()
        if not normalized_value or normalized_value in seen_values:
            continue
        seen_values.add(normalized_value)
        normalized_values.append(normalized_value)
    return normalized_values
