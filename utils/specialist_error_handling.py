from __future__ import annotations

from typing import Any

from contracts.agent_output import (
    AgentExecutionOutput,
    AgentExecutionStatus,
)


def build_failed_agent_output(
    *,
    owner_agent: str,
    code: str,
    category: str,
    message: str,
    details: dict[str, Any] | None = None,
    recommended_action: str = "mark_failed",
    can_retry: bool = False,
    reason: str | None = None,
) -> AgentExecutionOutput:
    diagnostic_details = dict(details or {})
    diagnostic_details.setdefault("owner_agent", owner_agent)
    diagnostic_details.setdefault("error_category", category)
    return AgentExecutionOutput(
        result={},
        logs=[message],
        status=AgentExecutionStatus.FAILED,
        warnings=[build_warning_message(category, recommended_action)],
        technical_errors=[
            {
                "message": message,
                "code": code,
                "category": category,
                "supervisor_recommendation": {
                    "can_retry": can_retry,
                    "recommended_action": recommended_action,
                    "reason": reason or build_recommendation_reason(category),
                },
                "details": diagnostic_details,
            }
        ],
    )


def classify_agent_exception(exc: Exception) -> dict[str, Any]:
    error_text = str(exc).strip()
    normalized_text = error_text.lower()
    details = {
        "exception_type": type(exc).__name__,
        "error": error_text,
    }

    if "timeout" in normalized_text or "timed out" in normalized_text:
        return {
            "code": "agent_timeout",
            "category": "timeout",
            "message": "Specialist agent execution timed out before returning a response.",
            "details": details,
            "recommended_action": "retry",
            "can_retry": True,
            "reason": "The step can be retried because the agent did not finish within the time budget.",
        }

    if "tool" in normalized_text:
        return {
            "code": "tool_invocation_failed",
            "category": "tool_invocation_error",
            "message": "Specialist agent failed while invoking an assigned tool.",
            "details": details,
            "recommended_action": "retry",
            "can_retry": True,
            "reason": "Retry is reasonable because the failure happened during tool access or tool execution.",
        }

    if any(
        keyword in normalized_text
        for keyword in {"prompt", "context length", "token", "response format"}
    ):
        return {
            "code": "prompt_execution_failed",
            "category": "prompt_error",
            "message": "Specialist agent could not complete the prompt execution successfully.",
            "details": details,
            "recommended_action": "escalate",
            "can_retry": False,
            "reason": "Escalation is recommended because the failure suggests a prompt or model contract issue.",
        }

    return {
        "code": "agent_execution_failed",
        "category": "execution_error",
        "message": "Specialist agent execution failed before producing a valid response.",
        "details": details,
        "recommended_action": "escalate",
        "can_retry": False,
        "reason": "Escalation is recommended because the step failed before a usable response was produced.",
    }


def ensure_consistent_agent_output(
    *,
    agent_output: AgentExecutionOutput,
    owner_agent: str,
    expected_result_format: dict[str, Any],
    raw_text: str,
) -> AgentExecutionOutput:
    if agent_output.status == AgentExecutionStatus.COMPLETED:
        if not agent_output.result:
            return build_failed_agent_output(
                owner_agent=owner_agent,
                code="empty_agent_result",
                category="empty_result",
                message="Specialist agent returned completed status with an empty result payload.",
                details={"raw_text": raw_text},
                recommended_action="retry",
                can_retry=True,
                reason="Retry is possible because the agent returned no usable result content.",
            )

        missing_result_keys = [
            key for key in expected_result_format if key not in agent_output.result
        ]
        if missing_result_keys:
            return build_failed_agent_output(
                owner_agent=owner_agent,
                code="inconsistent_agent_output",
                category="response_inconsistency",
                message="Specialist agent returned completed status with a result that does not match the expected contract.",
                details={
                    "missing_result_keys": missing_result_keys,
                    "raw_text": raw_text,
                },
                recommended_action="retry",
                can_retry=True,
                reason="Retry is possible because the response shape is inconsistent with the expected contract.",
            )

    if (
        agent_output.status == AgentExecutionStatus.WAITING_FOR_APPROVAL
        and not agent_output.supervisor_data.approval_required_action_ids
    ):
        return build_failed_agent_output(
            owner_agent=owner_agent,
            code="inconsistent_agent_output",
            category="response_inconsistency",
            message="Specialist agent returned waiting_for_approval without approval-required actions.",
            details={"raw_text": raw_text},
            recommended_action="mark_failed",
            can_retry=False,
            reason="The step should be marked failed because approval state has no actionable approval targets.",
        )

    if agent_output.status == AgentExecutionStatus.FAILED and not agent_output.technical_errors:
        agent_output.technical_errors = [
            {
                "message": "Specialist agent reported failure without diagnostic details.",
                "code": "missing_failure_diagnostics",
                "category": "response_inconsistency",
                "supervisor_recommendation": {
                    "can_retry": False,
                    "recommended_action": "mark_failed",
                    "reason": "The step should be marked failed because diagnostic details are missing.",
                },
                "details": {"owner_agent": owner_agent, "raw_text": raw_text},
            }
        ]
    return agent_output


def build_warning_message(category: str, recommended_action: str) -> str:
    return (
        f"Failure category: {category}. "
        f"Recommended Supervisor action: {recommended_action}."
    )


def build_recommendation_reason(category: str) -> str:
    if category == "timeout":
        return "The step exceeded its time budget before returning a valid payload."
    if category == "tool_invocation_error":
        return "The step failed during tool invocation or tool processing."
    if category == "prompt_error":
        return "The step failed due to prompt construction or model-response issues."
    if category == "empty_result":
        return "The step returned an empty payload that cannot be aggregated safely."
    if category == "response_inconsistency":
        return "The returned payload is inconsistent with the expected workflow contract."
    return "The step failed and requires Supervisor review."
