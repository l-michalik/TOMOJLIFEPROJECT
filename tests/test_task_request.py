import unittest
from threading import Lock
from time import sleep

from agents.supervisor import run_supervisor_agent
from contracts.task_request import InputStatus, OperationType, TaskRequest, TargetEnvironment
from contracts.task_response import (
    SpecialistAgentName,
    WorkflowLifecycleStatus,
    WorkflowPlanStep,
    WorkflowStepStatus,
)
from settings.supervisor import SUPERVISOR_SYSTEM_PROMPT
from utils.workflow_delegation import delegate_workflow_plan


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

    def test_workflow_delegation_supports_parallel_batches(self) -> None:
        task_request = TaskRequest.model_validate(
            {
                "request_id": "req-106",
                "source": "api",
                "user_id": "platform-engineer",
                "user_request": "Deploy billing-api to stage version 2026.04.14",
                "params": {
                    "priority": "medium",
                    "execution_options": {},
                },
            }
        )
        concurrency = ConcurrencyTracker()

        def fake_runner(step, _task_request, _dependency_results, _model):
            concurrency.enter()
            sleep(0.02)
            concurrency.leave()
            return {
                "result": {"step_id": step.step_id},
                "logs": [f"completed {step.step_id}"],
                "status": "completed",
            }

        result = delegate_workflow_plan(
            plan=build_parallel_test_plan(),
            task_request=task_request,
            model="test-model",
            execution_mode="parallel",
            step_runner=fake_runner,
        )

        self.assertEqual(result["lifecycle_status"], WorkflowLifecycleStatus.COMPLETED)
        self.assertGreaterEqual(concurrency.max_active, 2)
        self.assertEqual(result["delegated_step_ids"][:3], ["STEP-1", "STEP-2", "STEP-3"])

    def test_workflow_delegation_supports_sequential_execution(self) -> None:
        task_request = TaskRequest.model_validate(
            {
                "request_id": "req-108",
                "source": "api",
                "user_id": "platform-engineer",
                "user_request": "Deploy billing-api to stage version 2026.04.14",
                "params": {
                    "priority": "medium",
                    "execution_options": {},
                },
            }
        )
        concurrency = ConcurrencyTracker()

        def fake_runner(step, _task_request, _dependency_results, _model):
            concurrency.enter()
            sleep(0.02)
            concurrency.leave()
            return {
                "result": {"step_id": step.step_id},
                "logs": [f"completed {step.step_id}"],
                "status": "completed",
            }

        result = delegate_workflow_plan(
            plan=build_parallel_test_plan(),
            task_request=task_request,
            model="test-model",
            execution_mode="sequential",
            step_runner=fake_runner,
        )

        self.assertEqual(result["lifecycle_status"], WorkflowLifecycleStatus.COMPLETED)
        self.assertEqual(concurrency.max_active, 1)

    def test_workflow_delegation_blocks_missing_input_context(self) -> None:
        task_request = TaskRequest.model_validate(
            {
                "request_id": "req-107",
                "source": "api",
                "user_id": "platform-engineer",
                "user_request": "Deploy billing-api to stage version 2026.04.14",
                "params": {
                    "priority": "medium",
                    "execution_options": {},
                },
            }
        )
        plan = [
            WorkflowPlanStep(
                step_id="STEP-1",
                owner_agent=SpecialistAgentName.DEPLOYMENT_AGENT,
                task_description="Analyze deployment prerequisites.",
                agent_instruction="Return JSON.",
                step_order=1,
                depends_on=[],
                expected_output_json_format={"summary": "string"},
                start_conditions=["Validated input is available."],
                result_handoff_condition="Return the result as JSON.",
                required_input_context={"service_name": None},
                expected_result="Deployment prerequisites analyzed.",
                status=WorkflowStepStatus.PLANNED,
            ),
            WorkflowPlanStep(
                step_id="STEP-2",
                owner_agent=SpecialistAgentName.INFRA_AGENT,
                task_description="Analyze infrastructure dependencies.",
                agent_instruction="Return JSON.",
                step_order=2,
                depends_on=["STEP-1"],
                expected_output_json_format={"summary": "string"},
                start_conditions=["Step 1 completed."],
                result_handoff_condition="Return the result as JSON.",
                required_input_context={"environment": "stage"},
                expected_result="Infrastructure dependencies analyzed.",
                status=WorkflowStepStatus.PLANNED,
            ),
        ]

        result = delegate_workflow_plan(
            plan=plan,
            task_request=task_request,
            model="test-model",
            execution_mode="sequential",
            step_runner=lambda *_: {
                "result": {"unexpected": True},
                "logs": [],
                "status": "completed",
            },
        )

        self.assertEqual(result["lifecycle_status"], WorkflowLifecycleStatus.BLOCKED)
        self.assertEqual(result["step_states"][0].status, WorkflowStepStatus.BLOCKED)
        self.assertEqual(result["step_states"][1].status, WorkflowStepStatus.BLOCKED)
        self.assertEqual(
            result["step_states"][0].status_reason,
            "Missing required input context.",
        )
        self.assertEqual(
            result["step_states"][1].status_reason,
            "Required dependency did not reach completed status.",
        )

class ConcurrencyTracker:
    def __init__(self) -> None:
        self._lock = Lock()
        self._active = 0
        self.max_active = 0

    def enter(self) -> None:
        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)

    def leave(self) -> None:
        with self._lock:
            self._active -= 1


def build_parallel_test_plan() -> list[WorkflowPlanStep]:
    return [
        WorkflowPlanStep(
            step_id="STEP-1",
            owner_agent=SpecialistAgentName.DEPLOYMENT_AGENT,
            task_description="Analyze deployment prerequisites.",
            agent_instruction="Return JSON.",
            step_order=1,
            depends_on=[],
            expected_output_json_format={"summary": "string"},
            start_conditions=["Validated input is available."],
            result_handoff_condition="Return the result as JSON.",
            required_input_context={"service_name": "billing-api"},
            expected_result="Deployment prerequisites analyzed.",
            status=WorkflowStepStatus.PLANNED,
        ),
        WorkflowPlanStep(
            step_id="STEP-2",
            owner_agent=SpecialistAgentName.INFRA_AGENT,
            task_description="Analyze infrastructure dependencies.",
            agent_instruction="Return JSON.",
            step_order=2,
            depends_on=[],
            expected_output_json_format={"summary": "string"},
            start_conditions=["Validated input is available."],
            result_handoff_condition="Return the result as JSON.",
            required_input_context={"environment": "stage"},
            expected_result="Infrastructure dependencies analyzed.",
            status=WorkflowStepStatus.PLANNED,
        ),
        WorkflowPlanStep(
            step_id="STEP-3",
            owner_agent=SpecialistAgentName.CI_CD_AGENT,
            task_description="Analyze pipeline impact.",
            agent_instruction="Return JSON.",
            step_order=3,
            depends_on=[],
            expected_output_json_format={"summary": "string"},
            start_conditions=["Validated input is available."],
            result_handoff_condition="Return the result as JSON.",
            required_input_context={"pipeline": "default"},
            expected_result="CI/CD impact analyzed.",
            status=WorkflowStepStatus.PLANNED,
        ),
        WorkflowPlanStep(
            step_id="STEP-4",
            owner_agent=SpecialistAgentName.DEPLOYMENT_AGENT,
            task_description="Prepare rollout strategy.",
            agent_instruction="Return JSON.",
            step_order=4,
            depends_on=["STEP-1", "STEP-2", "STEP-3"],
            expected_output_json_format={"summary": "string"},
            start_conditions=["Previous steps completed."],
            result_handoff_condition="Return the result as JSON.",
            required_input_context={"service_name": "billing-api"},
            expected_result="Rollout strategy prepared.",
            status=WorkflowStepStatus.PLANNED,
        ),
    ]


if __name__ == "__main__":
    unittest.main()
