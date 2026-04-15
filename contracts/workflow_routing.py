from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class SpecialistDomain(str, Enum):
    DEPLOYMENT = "deployment"
    INFRASTRUCTURE = "infrastructure"
    CI_CD = "ci_cd"


class RoutingDecisionType(str, Enum):
    DIRECT = "direct"
    MIXED = "mixed"
    AMBIGUOUS = "ambiguous"


class DomainRoutingSignal(BaseModel):
    domain: SpecialistDomain
    score: int = 0
    reasons: list[str] = Field(default_factory=list)


class TaskRoutingDecision(BaseModel):
    primary_domain: SpecialistDomain | None = None
    supporting_domains: list[SpecialistDomain] = Field(default_factory=list)
    matched_domains: list[SpecialistDomain] = Field(default_factory=list)
    decision_type: RoutingDecisionType
    requires_human_resolution: bool = False
    ambiguity_reason: str | None = None
    signals: list[DomainRoutingSignal] = Field(default_factory=list)

