import os
import unittest

from settings.supervisor import (
    APP_AI_MODE_ENV,
    APP_AI_MODE_LIVE,
    APP_AI_MODE_MOCK,
    get_app_ai_mode,
    has_openai_api_key,
    is_live_ai_enabled,
)
from contracts.task_response import SpecialistAgentName
from utils.workflow_logging import (
    PROMPT_LOG_MODE_FULL,
    PROMPT_LOG_MODE_GENERIC,
    PROMPT_LOG_MODE_OFF,
    build_prompt_log_box_body,
    build_prompt_log_content,
    build_response_log_box_body,
    build_response_log_content,
    get_prompt_log_mode,
    get_response_log_mode,
)
from utils.workflow_delegation import (
    build_step_request_log_summary,
    build_step_response_log_summary,
)


class WorkflowLoggingTests(unittest.TestCase):
    def test_get_app_ai_mode_defaults_to_mock(self) -> None:
        previous_value = os.environ.get(APP_AI_MODE_ENV)
        try:
            os.environ.pop(APP_AI_MODE_ENV, None)
            self.assertEqual(get_app_ai_mode(), APP_AI_MODE_MOCK)
        finally:
            if previous_value is None:
                os.environ.pop(APP_AI_MODE_ENV, None)
            else:
                os.environ[APP_AI_MODE_ENV] = previous_value

    def test_get_app_ai_mode_falls_back_to_mock_for_invalid_value(self) -> None:
        previous_value = os.environ.get(APP_AI_MODE_ENV)
        try:
            os.environ[APP_AI_MODE_ENV] = "invalid"
            self.assertEqual(get_app_ai_mode(), APP_AI_MODE_MOCK)
        finally:
            if previous_value is None:
                os.environ.pop(APP_AI_MODE_ENV, None)
            else:
                os.environ[APP_AI_MODE_ENV] = previous_value

    def test_is_live_ai_enabled_requires_live_mode_and_api_key(self) -> None:
        previous_mode = os.environ.get(APP_AI_MODE_ENV)
        previous_key = os.environ.get("OPENAI_API_KEY")
        try:
            os.environ[APP_AI_MODE_ENV] = APP_AI_MODE_LIVE
            os.environ["OPENAI_API_KEY"] = "test-key"
            self.assertTrue(has_openai_api_key())
            self.assertTrue(is_live_ai_enabled())

            os.environ[APP_AI_MODE_ENV] = APP_AI_MODE_MOCK
            self.assertFalse(is_live_ai_enabled())

            os.environ[APP_AI_MODE_ENV] = APP_AI_MODE_LIVE
            os.environ["OPENAI_API_KEY"] = "   "
            self.assertFalse(has_openai_api_key())
            self.assertFalse(is_live_ai_enabled())
        finally:
            if previous_mode is None:
                os.environ.pop(APP_AI_MODE_ENV, None)
            else:
                os.environ[APP_AI_MODE_ENV] = previous_mode
            if previous_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous_key

    def test_build_prompt_log_content_returns_generic_prompt_in_generic_mode(self) -> None:
        self.assertEqual(
            build_prompt_log_content(
                prompt="secret task details\nwith more lines",
                generic_prompt="Execute the assigned workflow step.",
                mode=PROMPT_LOG_MODE_GENERIC,
            ),
            "Execute the assigned workflow step.",
        )

    def test_build_prompt_log_content_returns_full_prompt_in_full_mode(self) -> None:
        self.assertEqual(
            build_prompt_log_content(
                prompt="full prompt body",
                generic_prompt="Execute the assigned workflow step.",
                mode=PROMPT_LOG_MODE_FULL,
            ),
            "full prompt body",
        )

    def test_build_prompt_log_content_returns_none_in_off_mode(self) -> None:
        self.assertIsNone(
            build_prompt_log_content(
                prompt="full prompt body",
                generic_prompt="Execute the assigned workflow step.",
                mode=PROMPT_LOG_MODE_OFF,
            )
        )

    def test_get_prompt_log_mode_falls_back_to_generic_for_invalid_value(self) -> None:
        previous_value = os.environ.get("AI_REQUEST_LOG_PROMPT_MODE")
        try:
            os.environ["AI_REQUEST_LOG_PROMPT_MODE"] = "invalid"
            self.assertEqual(get_prompt_log_mode(), PROMPT_LOG_MODE_GENERIC)
        finally:
            if previous_value is None:
                os.environ.pop("AI_REQUEST_LOG_PROMPT_MODE", None)
            else:
                os.environ["AI_REQUEST_LOG_PROMPT_MODE"] = previous_value

    def test_build_response_log_content_returns_generic_response_in_generic_mode(self) -> None:
        self.assertEqual(
            build_response_log_content(
                response_text='{"status":"completed"}',
                generic_response="Agent returned the workflow step result.",
                mode=PROMPT_LOG_MODE_GENERIC,
            ),
            "Agent returned the workflow step result.",
        )

    def test_build_response_log_content_returns_full_response_in_full_mode(self) -> None:
        self.assertEqual(
            build_response_log_content(
                response_text='{"status":"completed"}',
                generic_response="Agent returned the workflow step result.",
                mode=PROMPT_LOG_MODE_FULL,
            ),
            '{"status":"completed"}',
        )

    def test_build_response_log_content_returns_none_in_off_mode(self) -> None:
        self.assertIsNone(
            build_response_log_content(
                response_text='{"status":"completed"}',
                generic_response="Agent returned the workflow step result.",
                mode=PROMPT_LOG_MODE_OFF,
            )
        )

    def test_get_response_log_mode_falls_back_to_generic_for_invalid_value(self) -> None:
        previous_value = os.environ.get("AI_RESPONSE_LOG_MODE")
        try:
            os.environ["AI_RESPONSE_LOG_MODE"] = "invalid"
            self.assertEqual(get_response_log_mode(), PROMPT_LOG_MODE_GENERIC)
        finally:
            if previous_value is None:
                os.environ.pop("AI_RESPONSE_LOG_MODE", None)
            else:
                os.environ["AI_RESPONSE_LOG_MODE"] = previous_value

    def test_build_prompt_log_box_body_includes_agent_and_action_summary(self) -> None:
        self.assertEqual(
            build_prompt_log_box_body(
                agent_name="DeploymentAgent",
                step_id="STEP-2",
                prompt_log_content="Execute the assigned workflow step.",
            ),
            "Agent: DeploymentAgent\nStep: STEP-2\nAction: Execute the assigned workflow step.",
        )

    def test_build_response_log_box_body_includes_agent_and_result_summary(self) -> None:
        self.assertEqual(
            build_response_log_box_body(
                agent_name="DeploymentAgent",
                step_id="STEP-2",
                response_log_content="Agent returned the workflow step result.",
            ),
            "Agent: DeploymentAgent\nStep: STEP-2\nResult: Agent returned the workflow step result.",
        )

    def test_build_step_request_log_summary_is_specific_per_agent(self) -> None:
        self.assertEqual(
            build_step_request_log_summary(SpecialistAgentName.DEPLOYMENT_AGENT),
            "Analyze the deployment plan and release actions.",
        )
        self.assertEqual(
            build_step_request_log_summary(SpecialistAgentName.RISK_POLICY_AGENT),
            "Review proposed actions for policy and approval requirements.",
        )

    def test_build_step_response_log_summary_is_specific_per_agent(self) -> None:
        self.assertEqual(
            build_step_response_log_summary(SpecialistAgentName.INFRA_AGENT),
            "Infrastructure analysis result received.",
        )
        self.assertEqual(
            build_step_response_log_summary(SpecialistAgentName.EXECUTION_AGENT),
            "Execution handoff result received.",
        )


if __name__ == "__main__":
    unittest.main()
