import unittest

from agents.supervisor import run_supervisor_agent
from contracts.task_request import InputStatus, OperationType, TaskRequest, TargetEnvironment
from contracts.task_response import (
    SpecialistAgentName,
    WorkflowLifecycleStatus,
    WorkflowStepStatus,
)
from settings.supervisor import SUPERVISOR_SYSTEM_PROMPT


class TaskRequestParsingTests(unittest.TestCase):
    def test_supervisor_prompt_matches_required_plan_fields(self) -> None:
        self.assertIn("agent_instruction", SUPERVISOR_SYSTEM_PROMPT)
        self.assertIn("expected_output_json_format", SUPERVISOR_SYSTEM_PROMPT)
        self.assertIn("start_conditions", SUPERVISOR_SYSTEM_PROMPT)
        self.assertIn("result_handoff_condition", SUPERVISOR_SYSTEM_PROMPT)

    def test_builds_standardized_work_item_from_user_request(self) -> None:
        task_request = TaskRequest.model_validate(
            {
                "request_id": "req-101",
                "source": "api",
                "user_id": "alice",
                "user_request": "Deploy billing-api to stage version 2026.04.14 without downtime",
                "params": {
                    "priority": "high",
                    "execution_options": {},
                },
            }
        )

        self.assertEqual(task_request.input_status, InputStatus.READY_FOR_PLANNING)
        self.assertEqual(
            task_request.standardized_work_item.service_name,
            "billing-api",
        )
        self.assertEqual(
            task_request.standardized_work_item.target_environment,
            TargetEnvironment.STAGE,
        )
        self.assertEqual(
            task_request.standardized_work_item.operation_type,
            OperationType.DEPLOY,
        )
        self.assertEqual(
            task_request.standardized_work_item.execution_parameters["release_version"],
            "2026.04.14",
        )
        self.assertIn("no_downtime", task_request.standardized_work_item.constraints)

    def test_marks_missing_semantic_fields_for_clarification(self) -> None:
        task_request = TaskRequest.model_validate(
            {
                "request_id": "req-102",
                "source": "chat",
                "user_id": "alice",
                "user_request": "Please help with this task",
                "params": {
                    "priority": "medium",
                    "conversation_id": "conv-22",
                    "execution_options": {},
                },
            }
        )

        self.assertEqual(task_request.input_status, InputStatus.NEEDS_CLARIFICATION)
        field_names = {item.field_name for item in task_request.clarification_items}
        self.assertIn("standardized_work_item.service_name", field_names)
        self.assertIn("standardized_work_item.target_environment", field_names)
        self.assertIn("standardized_work_item.operation_type", field_names)

        response = run_supervisor_agent(task_request=task_request)
        self.assertEqual(response.state.lifecycle_status, WorkflowLifecycleStatus.NEEDS_CLARIFICATION)
        self.assertEqual(response.state.request_id, "req-102")
        self.assertEqual(response.state.source.value, "chat")
        self.assertEqual(len(response.state.decision_history), 2)
        self.assertIsNotNone(response.state.timestamps.received_at)
        self.assertIsNotNone(response.state.timestamps.clarification_requested_at)

    def test_supports_legacy_payload_mapping(self) -> None:
        task_request = TaskRequest.model_validate(
            {
                "request_id": "req-103",
                "source": "jira",
                "user_id": "platform-engineer",
                "task_description": "Restart payments-api on production after approval",
                "parameters": {
                    "service_name": "payments-api",
                },
                "context": {
                    "environment": "prod",
                    "priority": "low",
                    "ticket_id": "OPS-10",
                },
            }
        )

        self.assertEqual(task_request.input_status, InputStatus.READY_FOR_PLANNING)
        self.assertEqual(
            task_request.standardized_work_item.operation_type,
            OperationType.RESTART,
        )
        self.assertEqual(
            task_request.standardized_work_item.target_environment,
            TargetEnvironment.PROD,
        )
        self.assertIn(
            "requires_approval",
            task_request.standardized_work_item.constraints,
        )

    def test_supervisor_builds_structured_plan_with_base_and_task_specific_steps(self) -> None:
        task_request = TaskRequest.model_validate(
            {
                "request_id": "req-104",
                "source": "api",
                "user_id": "platform-engineer",
                "user_request": "Deploy billing-api to stage version 2026.04.14 without downtime",
                "params": {
                    "priority": "high",
                    "execution_options": {},
                },
            }
        )

        response = run_supervisor_agent(task_request=task_request)

        self.assertEqual(response.status.value, "planned")
        self.assertFalse(response.requires_user_approval)
        self.assertEqual(len(response.plan), 7)
        self.assertEqual(response.state.lifecycle_status, WorkflowLifecycleStatus.COMPLETED)
        self.assertEqual(response.state.current_stage.value, "completed")
        self.assertEqual(len(response.state.plan_steps), len(response.plan))
        self.assertIsNone(response.state.resume_data.next_step_id)
        self.assertEqual(response.state.resume_data.checkpoint_id, "req-104:checkpoint:delegation")
        self.assertEqual(response.state.decision_history[-1].decision_id, "DEC-4")
        self.assertEqual(
            [step.owner_agent for step in response.plan[:3]],
            [
                SpecialistAgentName.DEPLOYMENT_AGENT,
                SpecialistAgentName.INFRA_AGENT,
                SpecialistAgentName.CI_CD_AGENT,
            ],
        )
        self.assertEqual(response.plan[3].owner_agent, SpecialistAgentName.DEPLOYMENT_AGENT)
        self.assertTrue(response.plan[0].agent_instruction)
        self.assertIn("proposed_actions", response.plan[0].expected_output_json_format)
        self.assertTrue(response.plan[0].start_conditions)
        self.assertTrue(response.plan[0].result_handoff_condition)
        self.assertEqual(response.plan[4].owner_agent, SpecialistAgentName.RISK_POLICY_AGENT)
        self.assertEqual(response.plan[5].owner_agent, SpecialistAgentName.EXECUTION_AGENT)
        self.assertEqual(response.plan[5].status, WorkflowStepStatus.COMPLETED)
        self.assertEqual(
            response.plan[6].owner_agent,
            SpecialistAgentName.HUMAN_REVIEW_INTERFACE,
        )
        self.assertTrue(all(step.status == WorkflowStepStatus.COMPLETED for step in response.plan))
        self.assertEqual(len(response.state.resume_data.delegated_step_ids), 7)
        self.assertIsNotNone(response.state.timestamps.completed_at)
        self.assertTrue(response.state.plan_steps[0].response)
        self.assertTrue(response.state.plan_steps[0].logs)
        self.assertIsNotNone(response.state.aggregation)
        self.assertEqual(
            response.state.aggregation.successful_step_ids,
            [step.step_id for step in response.plan],
        )
        self.assertFalse(response.state.aggregation.problematic_step_ids)
        self.assertFalse(response.state.aggregation.has_partial_result)

    def test_supervisor_adds_approval_gate_for_production_restart(self) -> None:
        task_request = TaskRequest.model_validate(
            {
                "request_id": "req-105",
                "source": "jira",
                "user_id": "platform-engineer",
                "user_request": "Restart payments-api on production after approval",
                "params": {
                    "priority": "high",
                    "ticket_id": "OPS-105",
                    "execution_options": {
                        "service_name": "payments-api",
                    },
                    "target_environment": "prod",
                },
            }
        )

        response = run_supervisor_agent(task_request=task_request)

        self.assertTrue(response.requires_user_approval)
        self.assertIn("production_change", response.risk_flags)
        self.assertIn("explicit_approval_required", response.risk_flags)
        self.assertEqual(len(response.plan), 8)
        self.assertEqual(
            response.state.lifecycle_status,
            WorkflowLifecycleStatus.WAITING_FOR_APPROVAL,
        )
        self.assertEqual(response.state.current_stage.value, "human_review")
        self.assertIn("STEP-6", response.state.resume_data.waiting_step_ids)
        self.assertIsNotNone(response.state.timestamps.waiting_for_approval_at)
        self.assertEqual(
            response.state.resume_data.delegated_step_ids,
            ["STEP-1", "STEP-2", "STEP-3", "STEP-4", "STEP-5"],
        )
        approval_step = response.plan[5]
        execution_step = response.plan[6]
        final_report_step = response.plan[7]
        for step in response.plan[:5]:
            self.assertEqual(step.status, WorkflowStepStatus.COMPLETED)
        self.assertEqual(
            approval_step.owner_agent,
            SpecialistAgentName.HUMAN_REVIEW_INTERFACE,
        )
        self.assertEqual(approval_step.status, WorkflowStepStatus.WAITING_FOR_APPROVAL)
        self.assertTrue(approval_step.requires_user_approval)
        self.assertEqual(execution_step.owner_agent, SpecialistAgentName.EXECUTION_AGENT)
        self.assertEqual(execution_step.status, WorkflowStepStatus.BLOCKED)
        self.assertEqual(execution_step.depends_on, ["STEP-6"])
        self.assertEqual(final_report_step.status, WorkflowStepStatus.BLOCKED)
        self.assertIsNotNone(response.state.aggregation)
        self.assertEqual(response.state.aggregation.waiting_step_ids, ["STEP-6"])
        self.assertIn("STEP-7", response.state.aggregation.blocked_step_ids)
        self.assertEqual(response.state.aggregation.next_decision, "await_user_approval")
        self.assertTrue(response.state.aggregation.has_partial_result)

if __name__ == "__main__":
    unittest.main()
