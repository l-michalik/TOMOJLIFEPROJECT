from __future__ import annotations

from typing import Any, Sequence

from deepagents import create_deep_agent

from agents.ci_cd_agent import CICDAgent
from agents.deployment_agent import DeploymentAgent
from agents.infra_agent import InfraAgent
from agents.specialist_base import BaseSpecialistAgent
from contracts.task_response import SpecialistAgentName
from utils.specialist_step_contract import (
    build_step_agent_name,
    build_step_request_log_summary,
    build_step_response_log_summary,
    build_step_system_prompt,
)


def build_specialist_agent(
    *,
    owner_agent: SpecialistAgentName,
    model: str,
    tools: Sequence[Any] | None = None,
    deep_agent_factory: Any | None = None,
) -> BaseSpecialistAgent:
    resolved_deep_agent_factory = deep_agent_factory or create_deep_agent
    if owner_agent == SpecialistAgentName.DEPLOYMENT_AGENT:
        return DeploymentAgent(
            model=model,
            tools=tools,
            deep_agent_factory=resolved_deep_agent_factory,
        )
    if owner_agent == SpecialistAgentName.INFRA_AGENT:
        return InfraAgent(
            model=model,
            tools=tools,
            deep_agent_factory=resolved_deep_agent_factory,
        )
    if owner_agent == SpecialistAgentName.CI_CD_AGENT:
        return CICDAgent(
            model=model,
            tools=tools,
            deep_agent_factory=resolved_deep_agent_factory,
        )

    return BaseSpecialistAgent(
        model=model,
        owner_agent=owner_agent.value,
        system_prompt=build_step_system_prompt(owner_agent),
        agent_name=build_step_agent_name(owner_agent),
        tools=tools,
        request_log_summary=build_step_request_log_summary(owner_agent),
        response_log_summary=build_step_response_log_summary(owner_agent),
        deep_agent_factory=resolved_deep_agent_factory,
    )
