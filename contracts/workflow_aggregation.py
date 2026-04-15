from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from contracts.agent_session_memory import AgentSessionMemory
from contracts.agent_output import (
    AgentArtifactReference,
    AgentTechnicalError,
    SupervisorAggregationPayload,
    SupervisorFailureRecommendation,
)


class AggregatedExecutionStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    NOT_EXECUTED = "not_executed"


class StepErrorDetails(BaseModel):
    message: str
    code: str | None = None
    category: str | None = None
    supervisor_recommendation: SupervisorFailureRecommendation | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AggregatedStepResult(BaseModel):
    step_id: str
    owner_agent: str
    step_status: str
    execution_status: AggregatedExecutionStatus
    result: dict[str, Any] | None = None
    logs: list[str] = Field(default_factory=list)
    artifacts: list[AgentArtifactReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    technical_errors: list[AgentTechnicalError] = Field(default_factory=list)
    supervisor_data: SupervisorAggregationPayload = Field(
        default_factory=SupervisorAggregationPayload
    )
    execution_details: dict[str, Any] = Field(default_factory=dict)
    session_memory: AgentSessionMemory | None = None
    error: StepErrorDetails | None = None
    is_problematic: bool = False


class WorkflowAggregationSummary(BaseModel):
    step_results: list[AggregatedStepResult] = Field(default_factory=list)
    successful_step_ids: list[str] = Field(default_factory=list)
    failed_step_ids: list[str] = Field(default_factory=list)
    blocked_step_ids: list[str] = Field(default_factory=list)
    waiting_step_ids: list[str] = Field(default_factory=list)
    problematic_step_ids: list[str] = Field(default_factory=list)
    has_partial_result: bool = False
    next_decision: str | None = None
