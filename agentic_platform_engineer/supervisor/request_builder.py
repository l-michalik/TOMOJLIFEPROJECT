from __future__ import annotations

from agentic_platform_engineer.contracts.supervisor_input import (
    IntakeAssessment,
    IntakeStatus,
    RawJsonObject,
    SupervisorInput,
    ValidationIssue,
    ValidationIssueCode,
)
from agentic_platform_engineer.contracts.supervisor_intake import (
    ParsedRequestDetails,
    SupervisorWorkItem,
    SupervisorWorkItemBuildResult,
)
from agentic_platform_engineer.supervisor.request_parser import normalize_supervisor_input
from agentic_platform_engineer.utils.request_parsing import (
    build_work_item_clarification_question,
    classify_task,
    parse_request_details_from_text,
    read_constraints,
    read_operation_type,
    service_name_is_required,
)
from agentic_platform_engineer.utils.text_utils import read_string, read_string_value


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
    user_request = read_string(payload, "user_request")
    parsed_text = parse_request_details_from_text(user_request)

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
):
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
    execution_params = dict(supervisor_input.params.execution_params)
    parsed_text = parse_request_details_from_text(supervisor_input.user_request)

    operation_type = read_operation_type(execution_params) or parsed_text.operation_type
    task_class = classify_task(operation_type)
    service_name = read_string_value(execution_params.get("service")) or parsed_text.service_name
    constraints = read_constraints(execution_params) or parsed_text.constraints

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

    if service_name_is_required(parsed_details) and parsed_details.service_name is None:
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
        build_work_item_clarification_question(issue.field_path, issue.code) for issue in blocking_issues
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
