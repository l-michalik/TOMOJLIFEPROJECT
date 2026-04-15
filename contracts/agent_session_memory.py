from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SessionMemoryAuthority(BaseModel):
    authoritative_source: str = "supervisor_workflow_state"
    scope: str = "single_step_execution"
    is_source_of_truth: bool = False
    usage_rule: str = (
        "Use this memory only as a local session snapshot. Resolve conflicts in favor of "
        "Supervisor-managed global workflow state."
    )


class SessionCommandRecord(BaseModel):
    summary: str
    source: str = "execution_details"


class SessionIntermediateResult(BaseModel):
    source_step_id: str
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentSessionMemory(BaseModel):
    request_id: str
    step_id: str
    owner_agent: str
    authority: SessionMemoryAuthority = Field(default_factory=SessionMemoryAuthority)
    current_task_context: dict[str, Any] = Field(default_factory=dict)
    recent_commands: list[SessionCommandRecord] = Field(default_factory=list)
    intermediate_results: list[SessionIntermediateResult] = Field(default_factory=list)
    environment_logs: list[str] = Field(default_factory=list)
    technical_notes: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime
