import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agents.deployment_agent import DeploymentAgent
from agents.specialist_factory import build_specialist_agent
from contracts.agent_input import AgentTaskType
from contracts.agent_output import AgentExecutionStatus
from contracts.task_request import TaskRequest
from contracts.task_response import SpecialistAgentName
from utils.workflow_delegation import run_specialist_step


class DeploymentAgentTests(unittest.TestCase):
    def test_deployment_agent_blocks_when_release_reference_is_missing_for_deploy(self) -> None:
        factory = FakeDeepAgentFactory("{}")
        agent = DeploymentAgent(model="openai:gpt-5.4-mini", deep_agent_factory=factory)

        output = agent.run(build_deployment_input())

        self.assertEqual(output.status, AgentExecutionStatus.BLOCKED)
        self.assertIn("release_reference", output.result["findings"][0])
        self.assertEqual(factory.invoke_count, 0)

    def test_deployment_agent_passes_allowed_tools_and_prompt_context_to_runtime_agent(self) -> None:
        factory = FakeDeepAgentFactory(
            response_text=json.dumps(
                {
                    "result": {"summary": "Deployment analysis completed."},
                    "logs": ["analysis complete"],
                    "status": "completed",
                }
            )
        )
        tools = ["tool:deployment-readiness", "tool:rollout-history"]
        agent = DeploymentAgent(
            model="openai:gpt-5.4-mini",
            tools=tools,
            deep_agent_factory=factory,
        )

        output = agent.run(
            build_deployment_input(
                execution_parameters={"release_version": "2026.04.15", "cluster": "stage-a"}
            )
        )

        self.assertEqual(output.status, AgentExecutionStatus.COMPLETED)
        self.assertEqual(factory.last_kwargs["tools"], tools)
        self.assertIn('"allowed_tools": [', factory.last_prompt)
        self.assertIn('"release_version": "2026.04.15"', factory.last_prompt)

    def test_deployment_agent_normalizes_partial_output_to_blocked(self) -> None:
        factory = FakeDeepAgentFactory(
            response_text=json.dumps(
                {
                    "result": {"summary": "Partial deployment result."},
                    "logs": ["some rollout checks were prepared"],
                    "status": "partial_execution",
                }
            )
        )
        agent = DeploymentAgent(
            model="openai:gpt-5.4-mini",
            deep_agent_factory=factory,
        )

        output = agent.run(
            build_deployment_input(
                execution_parameters={"release_version": "2026.04.15"},
            )
        )

        self.assertEqual(output.status, AgentExecutionStatus.BLOCKED)
        self.assertIn("normalized partial deployment output", output.logs[-1].lower())
        self.assertTrue(output.warnings)

    def test_specialist_factory_returns_dedicated_deployment_agent(self) -> None:
        agent = build_specialist_agent(
            owner_agent=SpecialistAgentName.DEPLOYMENT_AGENT,
            model="openai:gpt-5.4-mini",
        )

        self.assertIsInstance(agent, DeploymentAgent)

    def test_workflow_delegation_uses_deployment_agent_component_in_live_mode(self) -> None:
        step = build_workflow_step()
        task_request = build_task_request()
        fake_agent = FakeWorkflowDeploymentAgent()

        with patch("utils.workflow_delegation.is_live_ai_enabled", return_value=True):
            with patch("utils.workflow_delegation.build_specialist_agent", return_value=fake_agent):
                output = run_specialist_step(
                    step=step,
                    task_request=task_request,
                    dependency_results={},
                    model="openai:gpt-5.4-mini",
                )

        self.assertEqual(output["status"], "completed")
        self.assertEqual(fake_agent.last_payload.owner_agent, "DeploymentAgent")
        self.assertEqual(fake_agent.last_payload.task_type.value, "deployment_analysis")


class FakeDeepAgentFactory:
    def __init__(self, response_text: str = "{}") -> None:
        self.response_text = response_text
        self.last_kwargs: dict[str, object] | None = None
        self.last_prompt = ""
        self.invoke_count = 0

    def __call__(self, **kwargs):
        self.last_kwargs = kwargs
        return FakeCompiledAgent(self)


class FakeCompiledAgent:
    def __init__(self, factory: FakeDeepAgentFactory) -> None:
        self.factory = factory

    def invoke(self, payload: dict) -> dict:
        self.factory.invoke_count += 1
        self.factory.last_prompt = payload["messages"][0]["content"]
        return {"messages": [SimpleNamespace(content=self.factory.response_text)]}


class FakeWorkflowDeploymentAgent:
    def __init__(self) -> None:
        self.last_payload: dict | None = None

    def run(self, payload: dict) -> SimpleNamespace:
        self.last_payload = payload
        return SimpleNamespace(
            model_dump=lambda mode="json": {
                "result": {"summary": "Deployment analysis completed."},
                "logs": ["analysis complete"],
                "status": "completed",
            }
        )


def build_deployment_input(
    *,
    execution_parameters: dict | None = None,
) -> dict:
    return {
        "instruction": "Assess deployment readiness and return JSON only.",
        "context": {
            "request_id": "req-deployment-agent-101",
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
            "operation_type": "deploy",
            "execution_parameters": execution_parameters or {},
        },
        "execution_constraints": ["no_downtime"],
        "previous_step_outputs": {},
        "safety_flags": ["availability_constraint"],
        "depends_on": [],
        "expected_output_json_format": {"summary": "string"},
        "expected_result": "Deployment readiness is assessed.",
        "result_handoff_condition": "Return the structured output to Supervisor.",
    }


def build_task_request() -> TaskRequest:
    return TaskRequest.model_validate(
        {
            "request_id": "req-deployment-agent-live-101",
            "source": "api",
            "user_id": "platform-engineer",
            "user_request": "Deploy billing-api to stage version 2026.04.15",
            "params": {"priority": "medium", "execution_options": {}},
        }
    )


def build_workflow_step():
    from contracts.task_response import WorkflowPlanStep, WorkflowStepStatus

    return WorkflowPlanStep(
        step_id="STEP-1",
        owner_agent=SpecialistAgentName.DEPLOYMENT_AGENT,
        task_type=AgentTaskType.DEPLOYMENT_ANALYSIS,
        task_description="Analyze deployment prerequisites.",
        agent_instruction="Return JSON.",
        step_order=1,
        depends_on=[],
        expected_output_json_format={"summary": "string"},
        start_conditions=["Validated input is available."],
        result_handoff_condition="Return the result as JSON.",
        required_input_context={
            "service_name": "billing-api",
            "target_environment": "stage",
            "task_type": "deployment_analysis",
            "operation_type": "deploy",
            "execution_parameters": {"release_version": "2026.04.15"},
        },
        expected_result="Deployment prerequisites analyzed.",
        status=WorkflowStepStatus.PLANNED,
    )


if __name__ == "__main__":
    unittest.main()
