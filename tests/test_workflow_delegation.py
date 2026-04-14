import unittest
from threading import Lock
from time import sleep

from contracts.task_request import TaskRequest
from contracts.task_response import (
    SpecialistAgentName,
    WorkflowLifecycleStatus,
    WorkflowPlanStep,
    WorkflowStepStatus,
)
from contracts.workflow_aggregation import AggregatedExecutionStatus
from utils.workflow_delegation import delegate_workflow_plan


class WorkflowDelegationTests(unittest.TestCase):
    def test_workflow_delegation_supports_parallel_batches(self) -> None:
        task_request = build_task_request("req-106")
        concurrency = ConcurrencyTracker()

        def fake_runner(step, _task_request, _dependency_results, _model):
            concurrency.enter()
            sleep(0.02)
            concurrency.leave()
            return {"result": {"step_id": step.step_id}, "logs": [f"completed {step.step_id}"], "status": "completed"}

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
        task_request = build_task_request("req-108")
        concurrency = ConcurrencyTracker()

        def fake_runner(step, _task_request, _dependency_results, _model):
            concurrency.enter()
            sleep(0.02)
            concurrency.leave()
            return {"result": {"step_id": step.step_id}, "logs": [f"completed {step.step_id}"], "status": "completed"}

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
        task_request = build_task_request("req-107")
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
            step_runner=lambda *_: {"result": {"unexpected": True}, "logs": [], "status": "completed"},
        )

        self.assertEqual(result["lifecycle_status"], WorkflowLifecycleStatus.BLOCKED)
        self.assertEqual(result["step_states"][0].status, WorkflowStepStatus.BLOCKED)
        self.assertEqual(result["step_states"][1].status, WorkflowStepStatus.BLOCKED)
        self.assertEqual(result["step_states"][0].status_reason, "Missing required input context.")
        self.assertEqual(result["step_states"][1].status_reason, "Required dependency did not reach completed status.")
        self.assertEqual(result["aggregation"].blocked_step_ids, ["STEP-1", "STEP-2"])
        self.assertEqual(result["aggregation"].next_decision, "review_blocked_steps")

    def test_workflow_delegation_preserves_partial_results_for_failed_steps(self) -> None:
        task_request = build_task_request("req-109")

        def fake_runner(step, _task_request, _dependency_results, _model):
            if step.step_id == "STEP-2":
                return {
                    "result": {"step_id": step.step_id},
                    "logs": [f"failed {step.step_id}"],
                    "status": "failed",
                    "execution_details": {"attempt": 1},
                    "error": {"message": "Infrastructure validation failed.", "code": "infra_validation_failed"},
                }
            return {
                "result": {"step_id": step.step_id},
                "logs": [f"completed {step.step_id}"],
                "status": "completed",
                "execution_details": {"attempt": 1},
            }

        result = delegate_workflow_plan(
            plan=build_parallel_test_plan(),
            task_request=task_request,
            model="test-model",
            execution_mode="parallel",
            step_runner=fake_runner,
        )

        self.assertEqual(result["lifecycle_status"], WorkflowLifecycleStatus.FAILED)
        self.assertEqual(result["step_states"][0].status, WorkflowStepStatus.COMPLETED)
        self.assertEqual(result["step_states"][1].status, WorkflowStepStatus.FAILED)
        self.assertEqual(result["step_states"][1].error_details["code"], "infra_validation_failed")
        self.assertEqual(result["step_states"][3].status, WorkflowStepStatus.BLOCKED)
        self.assertEqual(result["aggregation"].successful_step_ids, ["STEP-1", "STEP-3"])
        self.assertEqual(result["aggregation"].failed_step_ids, ["STEP-2"])
        self.assertIn("STEP-4", result["aggregation"].blocked_step_ids)
        self.assertTrue(result["aggregation"].has_partial_result)
        self.assertEqual(result["aggregation"].next_decision, "review_failed_steps")
        failed_result = next(item for item in result["aggregation"].step_results if item.step_id == "STEP-2")
        self.assertEqual(failed_result.execution_status, AggregatedExecutionStatus.ERROR)
        self.assertTrue(failed_result.is_problematic)
        self.assertEqual(failed_result.error.message, "Infrastructure validation failed.")


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


def build_task_request(request_id: str) -> TaskRequest:
    return TaskRequest.model_validate(
        {
            "request_id": request_id,
            "source": "api",
            "user_id": "platform-engineer",
            "user_request": "Deploy billing-api to stage version 2026.04.14",
            "params": {"priority": "medium", "execution_options": {}},
        }
    )


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
