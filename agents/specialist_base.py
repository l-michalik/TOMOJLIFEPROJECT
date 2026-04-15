from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from deepagents import create_deep_agent

from contracts.agent_input import AgentExecutionInput
from contracts.agent_output import (
    AGENT_EXECUTION_STATUS_WORKFLOW_MEANINGS,
    AgentExecutionOutput,
    AgentExecutionStatus,
    build_agent_execution_output_format,
)
from settings.supervisor import get_specialist_max_output_tokens
from utils.specialist_error_handling import (
    build_failed_agent_output,
    classify_agent_exception,
    ensure_consistent_agent_output,
)
from utils.supervisor import read_last_message_text
from utils.workflow_logging import get_application_logger, log_ai_request, log_ai_response

ToolDefinition = Any
DeepAgentFactory = Callable[..., Any]
logger = get_application_logger("agents.specialist_base")


@dataclass(slots=True)
class SpecialistAgentWorkingContext:
    agent_input: AgentExecutionInput
    expected_output_json_format: dict[str, Any]
    workflow_status_meanings: dict[str, str]
    prompt_sections: list[str] = field(default_factory=list)


class BaseSpecialistAgent:
    def __init__(
        self,
        *,
        model: str,
        owner_agent: str,
        system_prompt: str,
        agent_name: str,
        tools: Sequence[ToolDefinition] | None = None,
        request_log_summary: str | None = None,
        response_log_summary: str | None = None,
        deep_agent_factory: DeepAgentFactory = create_deep_agent,
        max_output_tokens: int | None = None,
    ) -> None:
        self.model = model
        self.owner_agent = owner_agent
        self.system_prompt = system_prompt
        self.agent_name = agent_name
        self.tools = list(tools or [])
        self.request_log_summary = request_log_summary
        self.response_log_summary = response_log_summary
        self.deep_agent_factory = deep_agent_factory
        self.max_output_tokens = (
            max_output_tokens or get_specialist_max_output_tokens()
        )

    def run(self, payload: AgentExecutionInput | dict[str, Any]) -> AgentExecutionOutput:
        try:
            agent_input = AgentExecutionInput.model_validate(payload)
        except Exception as exc:
            return self.build_failed_output(
                code="invalid_agent_input",
                category="prompt_error",
                message="Specialist agent input contract validation failed.",
                details={"error": str(exc)},
                recommended_action="mark_failed",
                can_retry=False,
                reason="The step input is invalid, so Supervisor should mark the step as failed.",
            )

        working_context = self.build_working_context(agent_input)
        prompt = self.build_prompt(working_context)
        log_ai_request(
            logger,
            request_id=agent_input.context.request_id,
            model=self.model,
            prompt=prompt,
            agent_name=self.owner_agent,
            step_id=agent_input.step_id,
            generic_prompt=self.request_log_summary,
            owner_agent=self.owner_agent,
            task_description=agent_input.expected_result,
            status="delegated",
        )

        try:
            raw_text = self.invoke_prompt(prompt, working_context)
        except Exception as exc:
            classified_error = classify_agent_exception(exc)
            return self.build_failed_output(**classified_error)

        log_ai_response(
            logger,
            request_id=agent_input.context.request_id,
            model=self.model,
            response_text=raw_text,
            agent_name=self.owner_agent,
            step_id=agent_input.step_id,
            generic_response=self.response_log_summary,
            owner_agent=self.owner_agent,
        )
        parsed_output = self.parse_output(raw_text)
        return ensure_consistent_agent_output(
            agent_output=parsed_output,
            owner_agent=self.owner_agent,
            expected_result_format=working_context.expected_output_json_format,
            raw_text=raw_text,
        )

    def build_working_context(
        self,
        agent_input: AgentExecutionInput,
    ) -> SpecialistAgentWorkingContext:
        return SpecialistAgentWorkingContext(
            agent_input=agent_input,
            expected_output_json_format=agent_input.expected_output_json_format,
            workflow_status_meanings={
                status.value: meaning
                for status, meaning in AGENT_EXECUTION_STATUS_WORKFLOW_MEANINGS.items()
            },
            prompt_sections=self.build_additional_prompt_sections(agent_input),
        )

    def build_additional_prompt_sections(
        self,
        agent_input: AgentExecutionInput,
    ) -> list[str]:
        return []

    def build_prompt(self, working_context: SpecialistAgentWorkingContext) -> str:
        agent_input = working_context.agent_input
        sections = [
            "Execute the assigned workflow step using the standardized agent input contract.",
            (
                "Session memory rule:\n"
                "Treat session_memory as a short-term local cache for this single step. "
                "It is not an independent source of truth and must never override the "
                "Supervisor-managed workflow state."
            ),
            "Agent input JSON:\n" + agent_input.model_dump_json(indent=2),
            "Return only valid JSON with this structure:\n"
            + json.dumps(
                build_agent_execution_output_format(
                    working_context.expected_output_json_format
                ),
                ensure_ascii=True,
                indent=2,
            ),
            "The result payload must follow this expected format:\n"
            + json.dumps(
                working_context.expected_output_json_format,
                ensure_ascii=True,
            ),
            "Status meanings for workflow continuation:\n"
            + json.dumps(
                working_context.workflow_status_meanings,
                ensure_ascii=True,
                indent=2,
            ),
            "Output budget:\n"
            + (
                f"Keep the entire JSON response under approximately {self.max_output_tokens} "
                "tokens. Prefer short summaries, compact findings, and no repeated restatement "
                "of the input."
            ),
        ]
        sections.extend(working_context.prompt_sections)
        return "\n\n".join(sections)

    def get_tools(
        self,
        working_context: SpecialistAgentWorkingContext,
    ) -> Sequence[ToolDefinition]:
        return self.tools

    def invoke_prompt(
        self,
        prompt: str,
        working_context: SpecialistAgentWorkingContext,
    ) -> str:
        agent = self.deep_agent_factory(
            model=self.model,
            tools=self.get_tools(working_context),
            system_prompt=self.system_prompt,
            name=self.agent_name,
        )
        result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
        return read_last_message_text(result)

    def parse_output(self, raw_text: str) -> AgentExecutionOutput:
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            return self.build_failed_output(
                code="invalid_json_response",
                category="response_inconsistency",
                message="Specialist agent did not return valid JSON.",
                details={"error": str(exc), "raw_text": raw_text},
                recommended_action="retry",
                can_retry=True,
                reason="Retry is possible because the model response could not be parsed as JSON.",
            )

        try:
            return AgentExecutionOutput.model_validate(payload)
        except Exception as exc:
            return self.build_failed_output(
                code="invalid_agent_output",
                category="response_inconsistency",
                message="Specialist agent returned JSON that does not match the output contract.",
                details={"error": str(exc)},
                recommended_action="retry",
                can_retry=True,
                reason="Retry is possible because the returned JSON does not match the expected contract.",
            )

    def build_failed_output(
        self,
        *,
        code: str,
        category: str,
        message: str,
        details: dict[str, Any],
        recommended_action: str = "mark_failed",
        can_retry: bool = False,
        reason: str | None = None,
    ) -> AgentExecutionOutput:
        return build_failed_agent_output(
            owner_agent=self.owner_agent,
            code=code,
            category=category,
            message=message,
            details=details,
            recommended_action=recommended_action,
            can_retry=can_retry,
            reason=reason,
        )
