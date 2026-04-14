from __future__ import annotations

from agentic_platform_engineer.contracts.supervisor_input import (
    IntakeAssessment,
    IntakeStatus,
    RawJsonObject,
    RequestSource,
    SupervisorInput,
    SupervisorInputValidation,
    ValidationIssue,
    ValidationIssueCode,
)
from agentic_platform_engineer.utils.request_validation import (
    build_input_clarification_question,
    build_request_context,
    build_supervisor_params,
    collect_validation_issues,
    normalize_enum,
    normalize_required_string,
)


def normalize_supervisor_input(payload: RawJsonObject) -> SupervisorInputValidation:
    issues = collect_validation_issues(payload)

    normalized_input = SupervisorInput(
        request_id=normalize_required_string(payload, "request_id"),
        source=normalize_enum(payload, "source", RequestSource),
        user_request=normalize_required_string(payload, "user_request"),
        params=build_supervisor_params(payload),
        context=build_request_context(payload),
        intake=_build_intake_assessment(issues),
    )
    return SupervisorInputValidation(normalized_input=normalized_input, issues=issues)


def _build_intake_assessment(issues: tuple[ValidationIssue, ...]) -> IntakeAssessment:
    blocking_issues = tuple(issue for issue in issues if issue.blocks_planning)
    if not blocking_issues:
        return IntakeAssessment(status=IntakeStatus.READY_FOR_PLANNING)

    missing_fields = tuple(
        issue.field_path for issue in blocking_issues if issue.code is ValidationIssueCode.MISSING_REQUIRED
    )
    invalid_fields = tuple(
        issue.field_path for issue in blocking_issues if issue.code is not ValidationIssueCode.MISSING_REQUIRED
    )
    clarification_questions = tuple(
        build_input_clarification_question(issue.field_path, issue.code) for issue in blocking_issues
    )
    return IntakeAssessment(
        status=IntakeStatus.NEEDS_CLARIFICATION,
        missing_fields=missing_fields,
        invalid_fields=invalid_fields,
        clarification_questions=clarification_questions,
    )
