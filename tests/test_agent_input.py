import unittest

from pydantic import ValidationError

from contracts.agent_input import AgentExecutionInput, AgentTaskType
from contracts.task_request import TaskRequest
from utils.workflow_delegation import build_agent_execution_input
from utils.workflow_plan_builder import build_workflow_plan


class AgentExecutionInputTests(unittest.TestCase):
    def build_task_request(self) -> TaskRequest:
        return TaskRequest.model_validate(
            {
                "request_id": "req-agent-101",
                "source": "api",
                "user_id": "platform-engineer",
                "user_request": "Deploy billing-api to stage version 2026.04.14 without downtime",
                "params": {
                    "priority": "high",
                    "execution_options": {},
                },
            }
        )

    def test_builds_valid_agent_execution_input_from_workflow_step(self) -> None:
        task_request = self.build_task_request()
        workflow_step = build_workflow_plan(task_request)[0]

        agent_input = build_agent_execution_input(
            step=workflow_step,
            task_request=task_request,
            dependency_results={},
        )

        self.assertEqual(agent_input.step_id, "STEP-1")
        self.assertEqual(agent_input.owner_agent, "DeploymentAgent")
        self.assertEqual(agent_input.task_type, AgentTaskType.DEPLOYMENT_ANALYSIS)
        self.assertEqual(agent_input.context.request_id, "req-agent-101")
        self.assertEqual(agent_input.context.service_name, "billing-api")
        self.assertEqual(agent_input.target_environment.value, "stage")
        self.assertEqual(agent_input.technical_params["service_name"], "billing-api")
        self.assertEqual(agent_input.technical_params["target_environment"], "stage")
        self.assertEqual(
            agent_input.technical_params["task_type"],
            AgentTaskType.DEPLOYMENT_ANALYSIS.value,
        )
        self.assertIn("no_downtime", agent_input.execution_constraints)
        self.assertIn("availability_constraint", agent_input.safety_flags)
        self.assertTrue(agent_input.expected_output_json_format)

    def test_rejects_inconsistent_technical_params(self) -> None:
        with self.assertRaises(ValidationError):
            AgentExecutionInput.model_validate(
                {
                    "instruction": "Return JSON only.",
                    "context": {
                        "request_id": "req-agent-102",
                        "source": "api",
                        "user_id": "platform-engineer",
                        "user_request": "Deploy billing-api to stage",
                        "priority": "medium",
                        "service_name": "billing-api",
                    },
                    "step_id": "STEP-1",
                    "owner_agent": "DeploymentAgent",
                    "task_type": "deployment_analysis",
                    "target_environment": "stage",
                    "technical_params": {
                        "service_name": "payments-api",
                        "target_environment": "stage",
                        "task_type": "deployment_analysis",
                    },
                    "execution_constraints": ["no_downtime"],
                    "previous_step_outputs": {},
                    "safety_flags": ["high_priority"],
                    "depends_on": [],
                    "expected_output_json_format": {"summary": "string"},
                    "expected_result": "Deployment analysis is ready.",
                    "result_handoff_condition": "Forward JSON to Supervisor.",
                }
            )

    def test_rejects_missing_response_schema(self) -> None:
        with self.assertRaises(ValidationError):
            AgentExecutionInput.model_validate(
                {
                    "instruction": "Return JSON only.",
                    "context": {
                        "request_id": "req-agent-103",
                        "source": "api",
                        "user_id": "platform-engineer",
                        "user_request": "Deploy billing-api to stage",
                        "priority": "medium",
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
                    },
                    "execution_constraints": ["no_downtime"],
                    "previous_step_outputs": {},
                    "safety_flags": ["high_priority"],
                    "depends_on": [],
                    "expected_output_json_format": {},
                    "expected_result": "Deployment analysis is ready.",
                    "result_handoff_condition": "Forward JSON to Supervisor.",
                }
            )


if __name__ == "__main__":
    unittest.main()
