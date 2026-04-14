from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from supervisor_input import (
    IntakeAssessment,
    IntakeStatus,
    JsonValue,
    RawJsonObject,
    RequestContext,
    RequestPriority,
    RequestSource,
    SupervisorInput,
    TargetEnvironment,
    ValidationIssue,
    ValidationIssueCode,
    normalize_supervisor_input,
)


class SupervisorTaskClass(StrEnum):
    DEPLOYMENT = "deployment"
    INFRA = "infra"
    CI = "ci"


class OperationType(StrEnum):
    DEPLOY = "deploy"
    ROLLBACK = "rollback"
    INFRA_CHANGE = "infra_change"
    INFRA_PROVISION = "infra_provision"
    PIPELINE_RUN = "pipeline_run"
    PIPELINE_VALIDATE = "pipeline_validate"


@dataclass(slots=True, frozen=True)
class ParsedRequestDetails:
    service_name: str | None
    target_environment: TargetEnvironment | None
    priority: RequestPriority | None
    operation_type: OperationType | None
    task_class: SupervisorTaskClass | None
    execution_params: dict[str, JsonValue]
    constraints: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class SupervisorWorkItem:
    request_id: str | None
    source: RequestSource | None
    user_request: str | None
    service_name: str | None
    target_environment: TargetEnvironment | None
    priority: RequestPriority | None
    operation_type: OperationType | None
    task_class: SupervisorTaskClass | None
    execution_params: dict[str, JsonValue]
    constraints: tuple[str, ...]
    context: RequestContext | None
    intake: IntakeAssessment


@dataclass(slots=True, frozen=True)
class SupervisorWorkItemBuildResult:
    normalized_input: SupervisorInput
    work_item: SupervisorWorkItem
    issues: tuple[ValidationIssue, ...]
    enriched_payload: RawJsonObject

    @property
    def is_ready_for_planning(self) -> bool:
        return self.work_item.intake.status is IntakeStatus.READY_FOR_PLANNING


def build_supervisor_work_item(payload: RawJsonObject) -> SupervisorWorkItemBuildResult:
    enriched_payload = _build_enriched_payload(payload)
    normalized_input_validation = normalize_supervisor_input(enriched_payload)
    normalized_input = normalized_input_validation.normalized_input

    parsed_details = _parse_request_details(normalized_input)
    work_item_issues = normalized_input_validation.issues + _collect_work_item_issues(parsed_details)
    intake = _build_intake_assessment(work_item_issues)

    work_item = SupervisorWorkItem(
        request_id=normalized_input.request_id,
        source=normalized_input.source,
        user_request=normalized_input.user_request,
        service_name=parsed_details.service_name,
        target_environment=parsed_details.target_environment,
        priority=parsed_details.priority,
        operation_type=parsed_details.operation_type,
        task_class=parsed_details.task_class,
        execution_params=parsed_details.execution_params,
        constraints=parsed_details.constraints,
        context=normalized_input.context,
        intake=intake,
    )
    return SupervisorWorkItemBuildResult(
        normalized_input=normalized_input,
        work_item=work_item,
        issues=work_item_issues,
        enriched_payload=enriched_payload,
    )


def _build_enriched_payload(payload: RawJsonObject) -> RawJsonObject:
    enriched_payload: RawJsonObject = dict(payload)
    user_request = _read_string(payload, "user_request")
    parsed_text = _parse_request_text(user_request)

    params_payload = payload.get("params")
    if "params" not in payload or isinstance(params_payload, dict):
        enriched_payload["params"] = _build_enriched_params(payload, parsed_text)

    return enriched_payload


def _build_enriched_params(payload: RawJsonObject, parsed_text: ParsedRequestDetails) -> RawJsonObject:
    original_params = payload.get("params")
    params: RawJsonObject = dict(original_params) if isinstance(original_params, dict) else {}

    if "target_environment" not in params and parsed_text.target_environment is not None:
        params["target_environment"] = parsed_text.target_environment.value
    if "priority" not in params and parsed_text.priority is not None:
        params["priority"] = parsed_text.priority.value

    original_execution_params = params.get("execution_params")
    if "execution_params" not in params or isinstance(original_execution_params, dict):
        params["execution_params"] = _build_enriched_execution_params(params, parsed_text)

    return params


def _build_enriched_execution_params(
    params_payload: RawJsonObject,
    parsed_text: ParsedRequestDetails,
) -> dict[str, JsonValue]:
    original_execution_params = params_payload.get("execution_params")
    execution_params = (
        dict(original_execution_params) if isinstance(original_execution_params, dict) else {}
    )

    if "service" not in execution_params and parsed_text.service_name is not None:
        execution_params["service"] = parsed_text.service_name
    if "operation_type" not in execution_params and parsed_text.operation_type is not None:
        execution_params["operation_type"] = parsed_text.operation_type.value

    for field_name, value in parsed_text.execution_params.items():
        if field_name not in execution_params:
            execution_params[field_name] = value

    if "constraints" not in execution_params and parsed_text.constraints:
        execution_params["constraints"] = list(parsed_text.constraints)

    return execution_params


def _parse_request_details(supervisor_input: SupervisorInput) -> ParsedRequestDetails:
    user_request = supervisor_input.user_request
    execution_params = dict(supervisor_input.params.execution_params)
    parsed_text = _parse_request_text(user_request)

    operation_type = _read_operation_type(execution_params) or parsed_text.operation_type
    task_class = _classify_task(operation_type)

    service_name = _read_string_value(execution_params.get("service")) or parsed_text.service_name
    constraints = _read_constraints(execution_params) or parsed_text.constraints

    return ParsedRequestDetails(
        service_name=service_name,
        target_environment=supervisor_input.params.target_environment or parsed_text.target_environment,
        priority=supervisor_input.params.priority or parsed_text.priority,
        operation_type=operation_type,
        task_class=task_class,
        execution_params=execution_params,
        constraints=constraints,
    )


def _collect_work_item_issues(parsed_details: ParsedRequestDetails) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []

    if parsed_details.operation_type is None:
        issues.append(
            ValidationIssue(
                "work_item.operation_type",
                "operation_type is required for planning",
                ValidationIssueCode.MISSING_REQUIRED,
            )
        )

    if _service_name_is_required(parsed_details) and parsed_details.service_name is None:
        issues.append(
            ValidationIssue(
                "work_item.service_name",
                "service_name is required for this task type",
                ValidationIssueCode.MISSING_REQUIRED,
            )
        )

    return tuple(issues)


def _build_intake_assessment(issues: tuple[ValidationIssue, ...]) -> IntakeAssessment:
    blocking_issues = tuple(issue for issue in issues if _blocks_planning(issue))
    if not blocking_issues:
        return IntakeAssessment(status=IntakeStatus.READY_FOR_PLANNING)

    missing_fields = tuple(
        issue.field_path for issue in blocking_issues if issue.code is ValidationIssueCode.MISSING_REQUIRED
    )
    invalid_fields = tuple(
        issue.field_path for issue in blocking_issues if issue.code is not ValidationIssueCode.MISSING_REQUIRED
    )
    clarification_questions = tuple(
        _build_clarification_question(issue.field_path, issue.code) for issue in blocking_issues
    )
    return IntakeAssessment(
        status=IntakeStatus.NEEDS_CLARIFICATION,
        missing_fields=missing_fields,
        invalid_fields=invalid_fields,
        clarification_questions=clarification_questions,
    )


def _blocks_planning(issue: ValidationIssue) -> bool:
    return issue.code in {
        ValidationIssueCode.MISSING_REQUIRED,
        ValidationIssueCode.INVALID_TYPE,
        ValidationIssueCode.UNSUPPORTED_VALUE,
        ValidationIssueCode.INVALID_JSON_VALUE,
    }


def _build_clarification_question(field_path: str, issue_code: ValidationIssueCode) -> str:
    if field_path == "work_item.operation_type":
        return "What operation should Supervisor plan for this request?"
    if field_path == "work_item.service_name":
        return "Which service should be targeted by this request?"
    if field_path == "params.target_environment":
        return "Which target environment should be used?"
    if field_path == "params.priority":
        return "What priority should be assigned to this request?"
    if issue_code is ValidationIssueCode.INVALID_TYPE:
        return f"Could you provide {field_path} in the expected format?"
    return f"What value should be provided for {field_path}?"


def _parse_request_text(user_request: str | None) -> ParsedRequestDetails:
    normalized_text = _normalize_text(user_request)
    if normalized_text is None:
        return ParsedRequestDetails(
            service_name=None,
            target_environment=None,
            priority=None,
            operation_type=None,
            task_class=None,
            execution_params={},
            constraints=(),
        )

    operation_type = _extract_operation_type(normalized_text)
    return ParsedRequestDetails(
        service_name=_extract_service_name(normalized_text),
        target_environment=_extract_target_environment(normalized_text),
        priority=_extract_priority(normalized_text),
        operation_type=operation_type,
        task_class=_classify_task(operation_type),
        execution_params=_extract_execution_params(normalized_text),
        constraints=_extract_constraints(normalized_text),
    )


def _extract_service_name(text: str) -> str | None:
    patterns = (
        r"\bservice\s+(?P<service>[a-z0-9][a-z0-9_-]*)\b",
        r"\bdeploy\s+(?P<service>[a-z0-9][a-z0-9_-]*)\b",
        r"\brelease\s+(?P<service>[a-z0-9][a-z0-9_-]*)\b",
        r"\brollback\s+(?P<service>[a-z0-9][a-z0-9_-]*)\b",
        r"\bpipeline\s+for\s+(?P<service>[a-z0-9][a-z0-9_-]*)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match is not None:
            return match.group("service")
    return None


def _extract_target_environment(text: str) -> TargetEnvironment | None:
    if re.search(r"\b(prod|production)\b", text):
        return TargetEnvironment.PROD
    if re.search(r"\b(stage|staging)\b", text):
        return TargetEnvironment.STAGE
    if re.search(r"\b(dev|development)\b", text):
        return TargetEnvironment.DEV
    return None


def _extract_priority(text: str) -> RequestPriority | None:
    if re.search(r"\burgent\b", text):
        return RequestPriority.URGENT
    if re.search(r"\bhigh\b", text):
        return RequestPriority.HIGH
    if re.search(r"\bmedium\b", text):
        return RequestPriority.MEDIUM
    if re.search(r"\blow\b", text):
        return RequestPriority.LOW
    return None


def _extract_operation_type(text: str) -> OperationType | None:
    patterns: tuple[tuple[OperationType, tuple[str, ...]], ...] = (
        (OperationType.ROLLBACK, (r"\brollback\b", r"\broll back\b")),
        (OperationType.DEPLOY, (r"\bdeploy\b", r"\brelease\b")),
        (OperationType.INFRA_PROVISION, (r"\bprovision\b", r"\bcreate infrastructure\b")),
        (
            OperationType.INFRA_CHANGE,
            (r"\bconfigure\b", r"\bupdate infrastructure\b", r"\bscale\b", r"\bresize\b"),
        ),
        (
            OperationType.PIPELINE_VALIDATE,
            (r"\bvalidate pipeline\b", r"\bcheck pipeline\b", r"\bvalidate artifact\b"),
        ),
        (OperationType.PIPELINE_RUN, (r"\brun pipeline\b", r"\btrigger pipeline\b", r"\bbuild\b")),
    )
    for operation_type, operation_patterns in patterns:
        if any(re.search(pattern, text) for pattern in operation_patterns):
            return operation_type
    return None


def _extract_execution_params(text: str) -> dict[str, JsonValue]:
    execution_params: dict[str, JsonValue] = {}

    version = _match_group(text, r"\b(?:version|tag)\s+(?P<value>[a-z0-9._-]+)\b")
    region = _match_group(text, r"\bregion\s+(?P<value>[a-z0-9-]+)\b")
    change_window = _extract_change_window(text)
    rollout_mode = _extract_rollout_mode(text)

    if version is not None:
        execution_params["version"] = version
    if region is not None:
        execution_params["region"] = region
    if change_window is not None:
        execution_params["change_window"] = change_window
    if rollout_mode is not None:
        execution_params["rollout_mode"] = rollout_mode

    return execution_params


def _extract_constraints(text: str) -> tuple[str, ...]:
    detected_constraints: list[str] = []
    if re.search(r"\b(no downtime|zero downtime)\b", text):
        detected_constraints.append("no-downtime")
    if re.search(r"\b(outside business hours|after hours)\b", text):
        detected_constraints.append("outside-business-hours")
    if re.search(r"\bmanual approval\b", text):
        detected_constraints.append("manual-approval")
    return tuple(detected_constraints)


def _extract_change_window(text: str) -> str | None:
    if re.search(r"\bbusiness hours\b", text):
        return "business-hours"
    if re.search(r"\b(outside business hours|after hours)\b", text):
        return "after-hours"
    return None


def _extract_rollout_mode(text: str) -> str | None:
    if re.search(r"\bblue[- ]green\b", text):
        return "blue-green"
    if re.search(r"\bcanary\b", text):
        return "canary"
    if re.search(r"\brolling\b", text):
        return "rolling"
    return None


def _read_operation_type(execution_params: dict[str, JsonValue]) -> OperationType | None:
    normalized_value = _read_string_value(execution_params.get("operation_type"))
    if normalized_value is None:
        return None

    try:
        return OperationType(normalized_value.lower())
    except ValueError:
        return None


def _read_constraints(execution_params: dict[str, JsonValue]) -> tuple[str, ...]:
    constraints_value = execution_params.get("constraints")
    if not isinstance(constraints_value, list):
        return ()

    normalized_constraints = [
        value.strip()
        for value in constraints_value
        if isinstance(value, str) and value.strip()
    ]
    return tuple(normalized_constraints)


def _service_name_is_required(parsed_details: ParsedRequestDetails) -> bool:
    return parsed_details.task_class in {
        SupervisorTaskClass.DEPLOYMENT,
        SupervisorTaskClass.CI,
    }


def _classify_task(operation_type: OperationType | None) -> SupervisorTaskClass | None:
    if operation_type in {OperationType.DEPLOY, OperationType.ROLLBACK}:
        return SupervisorTaskClass.DEPLOYMENT
    if operation_type in {OperationType.INFRA_CHANGE, OperationType.INFRA_PROVISION}:
        return SupervisorTaskClass.INFRA
    if operation_type in {OperationType.PIPELINE_RUN, OperationType.PIPELINE_VALIDATE}:
        return SupervisorTaskClass.CI
    return None


def _match_group(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    if match is None:
        return None
    return match.group("value")


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    normalized_value = value.strip().lower()
    return normalized_value or None


def _read_string(payload: RawJsonObject, field_name: str) -> str | None:
    value = payload.get(field_name)
    if not isinstance(value, str):
        return None
    normalized_value = value.strip()
    return normalized_value or None


def _read_string_value(value: JsonValue | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized_value = value.strip()
    return normalized_value or None
