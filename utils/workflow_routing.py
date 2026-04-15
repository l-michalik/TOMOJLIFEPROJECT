from __future__ import annotations

from collections import defaultdict
from typing import Any

from contracts.task_request import OperationType, TaskRequest
from contracts.workflow_routing import (
    DomainRoutingSignal,
    RoutingDecisionType,
    SpecialistDomain,
    TaskRoutingDecision,
)

DOMAIN_KEYWORDS: dict[SpecialistDomain, tuple[str, ...]] = {
    SpecialistDomain.DEPLOYMENT: (
        "deploy",
        "deployment",
        "rollout",
        "rollback",
        "restart",
        "release candidate",
        "promote",
        "blue green",
        "canary",
        "helm",
        "image tag",
    ),
    SpecialistDomain.INFRASTRUCTURE: (
        "infra",
        "infrastructure",
        "cluster",
        "kubernetes",
        "terraform",
        "network",
        "dns",
        "ingress",
        "config",
        "configuration",
        "secret",
        "iam",
        "permission",
        "scale",
    ),
    SpecialistDomain.CI_CD: (
        "pipeline",
        "ci/cd",
        "cicd",
        "build",
        "test",
        "workflow",
        "github actions",
        "gitlab ci",
        "jenkins",
        "artifact",
        "promotion",
        "release flow",
    ),
}

PRIMARY_DOMAIN_BY_OPERATION: dict[OperationType, SpecialistDomain] = {
    OperationType.DEPLOY: SpecialistDomain.DEPLOYMENT,
    OperationType.ROLLBACK: SpecialistDomain.DEPLOYMENT,
    OperationType.RESTART: SpecialistDomain.DEPLOYMENT,
    OperationType.SCALE: SpecialistDomain.INFRASTRUCTURE,
    OperationType.CONFIGURE: SpecialistDomain.INFRASTRUCTURE,
    OperationType.PIPELINE: SpecialistDomain.CI_CD,
    OperationType.BUILD: SpecialistDomain.CI_CD,
    OperationType.TEST: SpecialistDomain.CI_CD,
    OperationType.RELEASE: SpecialistDomain.CI_CD,
}


def build_task_routing_decision(task_request: TaskRequest) -> TaskRoutingDecision:
    work_item = task_request.standardized_work_item
    domain_scores: dict[SpecialistDomain, int] = defaultdict(int)
    domain_reasons: dict[SpecialistDomain, list[str]] = defaultdict(list)
    request_blob = build_request_blob(task_request)

    primary_domain = (
        PRIMARY_DOMAIN_BY_OPERATION.get(work_item.operation_type)
        if work_item.operation_type is not None
        else None
    )
    if primary_domain is not None:
        domain_scores[primary_domain] += 4
        domain_reasons[primary_domain].append(
            f"operation_type:{work_item.operation_type.value}"
        )

    for domain, keywords in DOMAIN_KEYWORDS.items():
        for keyword in keywords:
            if keyword not in request_blob:
                continue
            domain_scores[domain] += 1
            domain_reasons[domain].append(f"keyword:{keyword}")

    if work_item.operation_type == OperationType.DIAGNOSE:
        domain_scores = boost_diagnostic_domains(
            domain_scores=domain_scores,
            domain_reasons=domain_reasons,
        )

    matched_domains = [
        domain for domain, score in domain_scores.items() if score > 0
    ]
    matched_domains.sort(key=lambda domain: (-domain_scores[domain], domain.value))

    if not matched_domains:
        return build_ambiguous_decision(
            domain_scores=domain_scores,
            domain_reasons=domain_reasons,
            ambiguity_reason="No deployment, infrastructure, or CI/CD routing signals were detected.",
        )

    highest_score = domain_scores[matched_domains[0]]
    top_domains = [
        domain for domain in matched_domains if domain_scores[domain] == highest_score
    ]
    if len(top_domains) > 1:
        return build_ambiguous_decision(
            domain_scores=domain_scores,
            domain_reasons=domain_reasons,
            ambiguity_reason=(
                "Routing signals point to multiple specialist domains with the same priority."
            ),
        )

    resolved_primary_domain = matched_domains[0]
    supporting_domains = matched_domains[1:]
    decision_type = (
        RoutingDecisionType.MIXED if supporting_domains else RoutingDecisionType.DIRECT
    )
    return TaskRoutingDecision(
        primary_domain=resolved_primary_domain,
        supporting_domains=supporting_domains,
        matched_domains=matched_domains,
        decision_type=decision_type,
        requires_human_resolution=False,
        signals=build_domain_signals(
            domain_scores=domain_scores,
            domain_reasons=domain_reasons,
        ),
    )


def build_routing_context(routing_decision: TaskRoutingDecision) -> dict[str, Any]:
    return {
        "decision_type": routing_decision.decision_type.value,
        "primary_domain": (
            routing_decision.primary_domain.value
            if routing_decision.primary_domain is not None
            else None
        ),
        "supporting_domains": [
            domain.value for domain in routing_decision.supporting_domains
        ],
        "matched_domains": [domain.value for domain in routing_decision.matched_domains],
        "requires_human_resolution": routing_decision.requires_human_resolution,
        "ambiguity_reason": routing_decision.ambiguity_reason,
        "signals": [
            {
                "domain": signal.domain.value,
                "score": signal.score,
                "reasons": signal.reasons,
            }
            for signal in routing_decision.signals
        ],
    }


def build_routing_risk_flags(routing_decision: TaskRoutingDecision) -> list[str]:
    risk_flags: list[str] = []
    if routing_decision.decision_type == RoutingDecisionType.MIXED:
        risk_flags.append("mixed_specialist_routing")
    if routing_decision.decision_type == RoutingDecisionType.AMBIGUOUS:
        risk_flags.append("ambiguous_specialist_routing")
    return risk_flags


def build_request_blob(task_request: TaskRequest) -> str:
    work_item = task_request.standardized_work_item
    request_parts: list[str] = [task_request.user_request.lower()]

    if work_item.service_name:
        request_parts.append(work_item.service_name.lower())
    for key, value in work_item.execution_parameters.items():
        request_parts.append(str(key).lower())
        request_parts.append(str(value).lower())
    for constraint in work_item.constraints:
        request_parts.append(constraint.lower())

    return " ".join(request_parts)


def boost_diagnostic_domains(
    *,
    domain_scores: dict[SpecialistDomain, int],
    domain_reasons: dict[SpecialistDomain, list[str]],
) -> dict[SpecialistDomain, int]:
    non_zero_domains = [domain for domain, score in domain_scores.items() if score > 0]
    if not non_zero_domains:
        domain_scores[SpecialistDomain.INFRASTRUCTURE] += 1
        domain_reasons[SpecialistDomain.INFRASTRUCTURE].append(
            "diagnostic_default:infrastructure"
        )
        return domain_scores

    for domain in non_zero_domains:
        domain_scores[domain] += 1
        domain_reasons[domain].append("diagnostic_signal")
    return domain_scores


def build_ambiguous_decision(
    *,
    domain_scores: dict[SpecialistDomain, int],
    domain_reasons: dict[SpecialistDomain, list[str]],
    ambiguity_reason: str,
) -> TaskRoutingDecision:
    signals = build_domain_signals(
        domain_scores=domain_scores,
        domain_reasons=domain_reasons,
    )
    matched_domains = [signal.domain for signal in signals if signal.score > 0]
    return TaskRoutingDecision(
        primary_domain=None,
        supporting_domains=[],
        matched_domains=matched_domains,
        decision_type=RoutingDecisionType.AMBIGUOUS,
        requires_human_resolution=True,
        ambiguity_reason=ambiguity_reason,
        signals=signals,
    )


def build_domain_signals(
    *,
    domain_scores: dict[SpecialistDomain, int],
    domain_reasons: dict[SpecialistDomain, list[str]],
) -> list[DomainRoutingSignal]:
    signals = [
        DomainRoutingSignal(
            domain=domain,
            score=domain_scores.get(domain, 0),
            reasons=domain_reasons.get(domain, []),
        )
        for domain in SpecialistDomain
    ]
    signals.sort(key=lambda signal: (-signal.score, signal.domain.value))
    return signals
