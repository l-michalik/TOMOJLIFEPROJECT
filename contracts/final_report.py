from typing import Any

from pydantic import BaseModel, Field


class FinalReportStepSummary(BaseModel):
    step_id: str
    owner_agent: str
    task_description: str
    status: str


class FinalReportAgentResult(BaseModel):
    agent_name: str
    step_id: str
    status: str
    summary: str
    artifacts: list[str] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
    error: str | None = None


class WorkflowFinalReport(BaseModel):
    request_id: str
    source: str
    final_status: str
    task_goal_summary: str
    planned_steps: list[FinalReportStepSummary] = Field(default_factory=list)
    executed_steps: list[FinalReportStepSummary] = Field(default_factory=list)
    specialist_results: list[FinalReportAgentResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    policy_blocked_actions: list[str] = Field(default_factory=list)
    approval_required_actions: list[str] = Field(default_factory=list)
    user_decisions_required: list[str] = Field(default_factory=list)
    log_references: list[str] = Field(default_factory=list)
    artifact_references: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    publication_message: str
