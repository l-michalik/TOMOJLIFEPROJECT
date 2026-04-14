import unittest

from contracts.task_request import InputStatus, OperationType, TaskRequest, TargetEnvironment


class TaskRequestParsingTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
