import unittest

from contracts.agent_output import (
    AGENT_EXECUTION_STATUS_WORKFLOW_MEANINGS,
    AgentExecutionOutput,
    AgentExecutionStatus,
)
from contracts.task_response import WorkflowStepStatus
from utils.specialist_step_contract import map_agent_status_to_workflow_status
from utils.workflow_delegation import normalize_step_response


class AgentExecutionOutputTests(unittest.TestCase):
    def test_maps_legacy_specialist_payload_to_standardized_output(self) -> None:
        output = AgentExecutionOutput.model_validate(
            {
                "result": {
                    "summary": "Deployment analysis completed.",
                    "focus": "deployment",
                    "findings": ["All release inputs are available."],
                    "proposed_actions": [
                        {
                            "action_id": "STEP-1-ACTION-1",
                            "action_type": "deploy",
                            "details": {"service_name": "billing-api"},
                        }
                    ],
                    "artifacts": ["s3://artifacts/release-notes.md"],
                },
                "logs": ["analysis complete"],
                "status": "completed",
            }
        )

        self.assertEqual(output.status, AgentExecutionStatus.COMPLETED)
        self.assertEqual(output.analysis_details[0].category, "deployment")
        self.assertEqual(output.recommended_actions[0].action_id, "STEP-1-ACTION-1")
        self.assertEqual(output.artifacts[0].uri, "s3://artifacts/release-notes.md")
        self.assertEqual(output.supervisor_data.produced_action_ids, ["STEP-1-ACTION-1"])

    def test_normalize_step_response_preserves_supervisor_aggregation_fields(self) -> None:
        normalized = normalize_step_response(
            {
                "result": {
                    "decisions": [
                        {
                            "action_id": "STEP-1-ACTION-1",
                            "allowed": True,
                            "requiresApproval": True,
                            "reason": "Approval required for production change.",
                        }
                    ]
                },
                "logs": ["policy review finished"],
                "status": "waiting_for_approval",
                "warnings": ["Production change detected."],
                "technical_errors": [],
            }
        )

        self.assertEqual(normalized["status"], WorkflowStepStatus.WAITING_FOR_APPROVAL)
        self.assertEqual(
            normalized["supervisor_data"].approval_required_action_ids,
            ["STEP-1-ACTION-1"],
        )
        self.assertEqual(normalized["supervisor_data"].next_decision, "await_user_approval")
        self.assertEqual(normalized["warnings"], ["Production change detected."])

    def test_status_meanings_cover_every_supported_status(self) -> None:
        self.assertEqual(
            set(AGENT_EXECUTION_STATUS_WORKFLOW_MEANINGS),
            set(AgentExecutionStatus),
        )
        self.assertEqual(
            map_agent_status_to_workflow_status(AgentExecutionStatus.BLOCKED),
            WorkflowStepStatus.BLOCKED,
        )
        self.assertEqual(
            map_agent_status_to_workflow_status(AgentExecutionStatus.WAITING_FOR_APPROVAL),
            WorkflowStepStatus.WAITING_FOR_APPROVAL,
        )


if __name__ == "__main__":
    unittest.main()
