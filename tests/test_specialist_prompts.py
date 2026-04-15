import unittest

from contracts.task_response import SpecialistAgentName
from utils.specialist_step_contract import build_step_system_prompt


class SpecialistPromptTests(unittest.TestCase):
    def test_deployment_prompt_is_loaded_from_file_for_runtime_steps(self) -> None:
        prompt = build_step_system_prompt(SpecialistAgentName.DEPLOYMENT_AGENT)

        self.assertIn("You are DeploymentAgent", prompt)
        self.assertIn("deploy_release", prompt)
        self.assertIn("restart_service", prompt)
        self.assertIn("validate_deployment_config", prompt)
        self.assertIn("collect_technical_logs", prompt)
        self.assertIn("return JSON only", prompt)

    def test_unknown_specialist_uses_generic_json_contract_prompt(self) -> None:
        prompt = build_step_system_prompt(SpecialistAgentName.RISK_POLICY_AGENT)

        self.assertIn("Return only valid JSON using the standardized agent output contract.", prompt)
        self.assertIn("Allowed statuses are completed, failed, blocked, and waiting_for_approval.", prompt)


if __name__ == "__main__":
    unittest.main()
