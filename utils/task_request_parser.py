from __future__ import annotations

import re
from typing import Any

ENVIRONMENT_ALIASES = {
    "dev": "dev",
    "development": "dev",
    "stage": "stage",
    "staging": "stage",
    "prod": "prod",
    "production": "prod",
}

OPERATION_KEYWORDS = {
    "rollback": ("rollback", "roll back"),
    "deploy": ("deploy", "rollout"),
    "restart": ("restart", "redeploy"),
    "scale": ("scale", "scal"),
    "configure": ("configure", "configuration", "config", "update config"),
    "diagnose": ("diagnose", "debug", "investigate", "troubleshoot", "check"),
    "pipeline": ("pipeline", "workflow", "ci/cd", "cicd"),
    "build": ("build",),
    "test": ("test", "tests"),
    "release": ("release",),
}

OPERATION_ALIASES = {
    "deploy": "deploy",
    "deployment": "deploy",
    "rollback": "rollback",
    "roll_back": "rollback",
    "restart": "restart",
    "redeploy": "restart",
    "scale": "scale",
    "configure": "configure",
    "configuration": "configure",
    "config": "configure",
    "diagnose": "diagnose",
    "debug": "diagnose",
    "investigate": "diagnose",
    "troubleshoot": "diagnose",
    "pipeline": "pipeline",
    "ci_cd": "pipeline",
    "cicd": "pipeline",
    "build": "build",
    "test": "test",
    "release": "release",
}

SERVICE_OPTION_KEYS = (
    "service_name",
    "service",
    "app",
    "app_name",
    "application",
    "application_name",
)

CONSTRAINT_PATTERNS = {
    "no_downtime": re.compile(r"\b(no downtime|without downtime)\b", re.IGNORECASE),
    "dry_run_only": re.compile(r"\b(dry[- ]run( only)?)\b", re.IGNORECASE),
    "outside_business_hours": re.compile(
        r"\b(outside business hours|after hours|out of hours)\b", re.IGNORECASE
    ),
    "requires_approval": re.compile(
        r"\b(requires approval|after approval|with approval)\b", re.IGNORECASE
    ),
}

STOPWORD_SERVICE_NAMES = {
    "service",
    "app",
    "application",
    "the",
    "a",
    "an",
    "to",
    "on",
    "for",
    "in",
    "dev",
    "stage",
    "prod",
    "development",
    "staging",
    "production",
}


def build_standardized_work_item(
    user_request: str,
    execution_options: dict[str, Any],
    declared_environment: str | None,
) -> dict[str, Any]:
    environment = extract_environment(
        user_request=user_request,
        execution_options=execution_options,
        declared_environment=declared_environment,
    )
    service_name = extract_service_name(
        user_request=user_request,
        execution_options=execution_options,
    )
    operation_type = extract_operation_type(
        user_request=user_request,
        execution_options=execution_options,
    )
    execution_parameters = extract_execution_parameters(
        user_request=user_request,
        execution_options=execution_options,
        service_name=service_name,
        environment=environment,
    )
    constraints = extract_constraints(
        user_request=user_request,
        execution_options=execution_options,
    )

    return {
        "service_name": service_name,
        "target_environment": environment,
        "operation_type": operation_type,
        "execution_parameters": execution_parameters,
        "constraints": constraints,
    }


def extract_environment(
    user_request: str, execution_options: dict[str, Any], declared_environment: str | None
) -> str | None:
    for candidate in (
        declared_environment,
        execution_options.get("target_environment"),
        execution_options.get("environment"),
        execution_options.get("env"),
    ):
        normalized_candidate = normalize_environment(candidate)
        if normalized_candidate:
            return normalized_candidate

    normalized_request = normalize_text(user_request)
    for alias, normalized_value in ENVIRONMENT_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", normalized_request):
            return normalized_value

    return None


def extract_service_name(user_request: str, execution_options: dict[str, Any]) -> str | None:
    for key in SERVICE_OPTION_KEYS:
        candidate = normalize_service_name(execution_options.get(key))
        if candidate:
            return candidate

    service_patterns = (
        r"\b(?:deploy|rollback|restart|scale|configure|diagnose|debug|investigate|build|test|release)\s+([a-z0-9][a-z0-9._-]*)\b",
        r"\b([a-z0-9][a-z0-9._-]*)\s+(?:service|app|application)\b",
        r"\bservice\s+([a-z0-9][a-z0-9._-]*)\b",
        r"\bapp(?:lication)?\s+([a-z0-9][a-z0-9._-]*)\b",
    )
    normalized_request = normalize_text(user_request)

    for pattern in service_patterns:
        match = re.search(pattern, normalized_request, re.IGNORECASE)
        if not match:
            continue
        candidate = normalize_service_name(match.group(1))
        if candidate:
            return candidate

    return None


def extract_operation_type(
    user_request: str, execution_options: dict[str, Any]
) -> str | None:
    explicit_operation = normalize_operation_type(
        execution_options.get("operation_type") or execution_options.get("operation")
    )
    if explicit_operation:
        return explicit_operation

    normalized_request = normalize_text(user_request)
    first_match: tuple[int, str] | None = None

    for operation_type, keywords in OPERATION_KEYWORDS.items():
        for keyword in keywords:
            position = normalized_request.find(keyword)
            if position == -1:
                continue
            if first_match is None or position < first_match[0]:
                first_match = (position, operation_type)

    if first_match:
        return first_match[1]

    return None


def extract_execution_parameters(
    user_request: str,
    execution_options: dict[str, Any],
    service_name: str | None,
    environment: str | None,
) -> dict[str, Any]:
    execution_parameters = dict(execution_options)

    if service_name:
        execution_parameters["service_name"] = service_name
    if environment:
        execution_parameters["target_environment"] = environment

    normalized_request = normalize_text(user_request)

    release_match = re.search(
        r"\b(?:version|release|tag|image)\s+([a-z0-9][a-z0-9._:/-]*)\b",
        normalized_request,
        re.IGNORECASE,
    )
    if release_match and "release_version" not in execution_parameters:
        execution_parameters["release_version"] = release_match.group(1)

    replica_match = re.search(
        r"\b(?:replicas?|instances?)\s*(?:to|=)?\s*(\d+)\b",
        normalized_request,
        re.IGNORECASE,
    )
    if replica_match and "replica_count" not in execution_parameters:
        execution_parameters["replica_count"] = int(replica_match.group(1))

    return execution_parameters


def extract_constraints(user_request: str, execution_options: dict[str, Any]) -> list[str]:
    constraints: list[str] = []
    raw_constraints = execution_options.get("constraints")

    if isinstance(raw_constraints, str):
        normalized_constraint = raw_constraints.strip()
        if normalized_constraint:
            constraints.append(normalized_constraint)
    elif isinstance(raw_constraints, list):
        for item in raw_constraints:
            if isinstance(item, str):
                normalized_constraint = item.strip()
                if normalized_constraint:
                    constraints.append(normalized_constraint)

    normalized_request = normalize_text(user_request)
    for constraint_name, pattern in CONSTRAINT_PATTERNS.items():
        if pattern.search(normalized_request) and constraint_name not in constraints:
            constraints.append(constraint_name)

    return constraints


def normalize_environment(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized_value = value.strip().lower()
    return ENVIRONMENT_ALIASES.get(normalized_value)


def normalize_operation_type(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized_value = value.strip().lower().replace("-", "_").replace(" ", "_")
    if not normalized_value:
        return None
    return OPERATION_ALIASES.get(normalized_value)


def normalize_service_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized_value = value.strip().lower()
    if not normalized_value or normalized_value in STOPWORD_SERVICE_NAMES:
        return None
    return normalized_value


def normalize_text(value: str) -> str:
    return value.strip().lower()
