import json
import unittest
from types import SimpleNamespace

from agents.specialist_base import BaseSpecialistAgent, SpecialistAgentWorkingContext
from contracts.agent_output import AgentExecutionStatus


class SpecialistBaseTests(unittest.TestCase):
    def test_base_agent_runs_standardized_execution_flow(self) -> None:
        factory = FakeDeepAgentFactory(
            response_text=json.dumps(
                {
                    "result": {"summary": "Deployment analysis completed."},
                    "logs": ["analysis complete"],
                    "status": "completed",
                }
            )
        )
        agent = ExampleSpecialistAgent(deep_agent_factory=factory)

        output = agent.run(build_valid_agent_input())

        self.assertEqual(output.status, AgentExecutionStatus.COMPLETED)
        self.assertEqual(output.result["summary"], "Deployment analysis completed.")
        self.assertEqual(factory.last_kwargs["tools"], ["tool:release-readiness"])
        self.assertIn("nightly-release-window", factory.last_prompt)
        self.assertEqual(factory.last_kwargs["name"], "deployment-agent")

    def test_base_agent_returns_failed_output_when_input_contract_is_invalid(self) -> None:
        agent = ExampleSpecialistAgent()

        output = agent.run({"instruction": "missing the rest of the contract"})

        self.assertEqual(output.status, AgentExecutionStatus.FAILED)
        self.assertEqual(output.technical_errors[0].code, "invalid_agent_input")

    def test_base_agent_returns_failed_output_for_invalid_json_response(self) -> None:
        factory = FakeDeepAgentFactory(response_text="not-json")
        agent = ExampleSpecialistAgent(deep_agent_factory=factory)

        output = agent.run(build_valid_agent_input())

        self.assertEqual(output.status, AgentExecutionStatus.FAILED)
        self.assertEqual(output.technical_errors[0].code, "invalid_json_response")

    def test_base_agent_returns_failed_output_when_execution_raises(self) -> None:
        factory = FakeDeepAgentFactory(raise_on_invoke=RuntimeError("tool backend unavailable"))
        agent = ExampleSpecialistAgent(deep_agent_factory=factory)

        output = agent.run(build_valid_agent_input())

        self.assertEqual(output.status, AgentExecutionStatus.FAILED)
        self.assertEqual(output.technical_errors[0].code, "agent_execution_failed")


class ExampleSpecialistAgent(BaseSpecialistAgent):
    def __init__(self, deep_agent_factory=None) -> None:
        super().__init__(
            model="openai:gpt-5.4-mini",
            owner_agent="DeploymentAgent",
            system_prompt="You are the deployment specialist.",
            agent_name="deployment-agent",
            request_log_summary="Analyze the deployment plan and release actions.",
            response_log_summary="Deployment analysis result received.",
            deep_agent_factory=deep_agent_factory or FakeDeepAgentFactory("{}"),
        )

    def build_additional_prompt_sections(self, agent_input) -> list[str]:
        return ["Working context note: nightly-release-window"]

    def get_tools(self, working_context: SpecialistAgentWorkingContext) -> list[str]:
        return ["tool:release-readiness"]


class FakeDeepAgentFactory:
    def __init__(
        self,
        response_text: str = "{}",
        raise_on_invoke: Exception | None = None,
    ) -> None:
        self.response_text = response_text
        self.raise_on_invoke = raise_on_invoke
        self.last_kwargs: dict | None = None
        self.last_prompt = ""

    def __call__(self, **kwargs):
        self.last_kwargs = kwargs
        return FakeCompiledAgent(self)


class FakeCompiledAgent:
    def __init__(self, factory: FakeDeepAgentFactory) -> None:
        self.factory = factory

    def invoke(self, payload: dict) -> dict:
        if self.factory.raise_on_invoke:
            raise self.factory.raise_on_invoke
        self.factory.last_prompt = payload["messages"][0]["content"]
        return {"messages": [SimpleNamespace(content=self.factory.response_text)]}


def build_valid_agent_input() -> dict:
    return {
        "instruction": "Assess deployment readiness and return JSON only.",
        "context": {
            "request_id": "req-agent-base-101",
            "source": "api",
            "user_id": "platform-engineer",
            "user_request": "Deploy billing-api to stage.",
            "priority": "high",
            "service_name": "billing-api",
        },
        "step_id": "STEP-1",
        "owner_agent": "DeploymentAgent",
        "task_type": "deployment_analysis",
        "target_environment": "stage",
        "technical_params": {
            "service_name": "billing-api",
            "target_environment": "stage",
            "task_type": "deployment_analysis",
            "release_version": "2026.04.15",
        },
        "execution_constraints": ["no_downtime"],
        "previous_step_outputs": {},
        "safety_flags": ["availability_constraint"],
        "depends_on": [],
        "expected_output_json_format": {"summary": "string"},
        "expected_result": "Deployment readiness is assessed.",
        "result_handoff_condition": "Return the structured output to Supervisor.",
    }


if __name__ == "__main__":
    unittest.main()
