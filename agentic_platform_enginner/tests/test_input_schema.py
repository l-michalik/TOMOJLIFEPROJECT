from __future__ import annotations

import json
from pathlib import Path
import unittest

from schema.input_schema import ValidationError, validate_task_input


def _valid_payload() -> dict[str, object]:
    return {
        "taskDescription": "Deploy a new version of the billing-api service to production.",
        "source": "jira",
        "requester": {
            "id": "u-12345",
            "role": "devops",
            "displayName": "John Smith",
        },
        "parameters": {
            "environment": "prod",
            "serviceName": "billing-api",
            "operation": "deploy",
            "targetVersion": "1.8.2",
            "approvalRequired": True,
            "dryRun": False,
            "timeoutSeconds": 900,
            "tags": ["release", "billing"],
        },
        "metadata": {
            "ticketId": "APE-142",
            "correlationId": "req-2026-04-13-0001",
        },
    }


EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


class ValidateTaskInputTests(unittest.TestCase):
    def test_accepts_valid_payload(self) -> None:
        validated = validate_task_input(_valid_payload())
        self.assertEqual(validated["requester"]["id"], "u-12345")

    def test_rejects_non_object_payload(self) -> None:
        with self.assertRaisesRegex(ValidationError, "Payload must be a JSON object."):
            validate_task_input("invalid")

    def test_rejects_unknown_top_level_field(self) -> None:
        payload = _valid_payload()
        payload["unexpected"] = "value"

        with self.assertRaisesRegex(ValidationError, "Unknown field\\(s\\) in root: unexpected."):
            validate_task_input(payload)

    def test_rejects_short_task_description(self) -> None:
        payload = _valid_payload()
        payload["taskDescription"] = "Too short"

        with self.assertRaisesRegex(ValidationError, "Field 'taskDescription' must be at least 10 characters long."):
            validate_task_input(payload)

    def test_rejects_wrong_boolean_type(self) -> None:
        payload = _valid_payload()
        payload["parameters"] = {**payload["parameters"], "approvalRequired": "true"}  # type: ignore[arg-type]

        with self.assertRaisesRegex(ValidationError, "Field 'parameters.approvalRequired' must be boolean when provided."):
            validate_task_input(payload)

    def test_rejects_empty_parameters_object(self) -> None:
        payload = _valid_payload()
        payload["parameters"] = {}

        with self.assertRaisesRegex(ValidationError, "Field 'parameters' must contain at least 1 property."):
            validate_task_input(payload)

    def test_rejects_empty_metadata_object(self) -> None:
        payload = _valid_payload()
        payload["source"] = "api"
        payload["metadata"] = {}

        with self.assertRaisesRegex(ValidationError, "Field 'metadata' must contain at least 1 property."):
            validate_task_input(payload)

    def test_rejects_empty_tags_array(self) -> None:
        payload = _valid_payload()
        payload["parameters"] = {**payload["parameters"], "tags": []}  # type: ignore[arg-type]

        with self.assertRaisesRegex(ValidationError, "Field 'parameters.tags' must contain at least 1 entries."):
            validate_task_input(payload)

    def test_rejects_invalid_nested_structure(self) -> None:
        payload = _valid_payload()
        payload["requester"] = []

        with self.assertRaisesRegex(ValidationError, "Field 'requester' must be an object."):
            validate_task_input(payload)

    def test_example_payloads_are_valid(self) -> None:
        for payload_path in sorted(EXAMPLES_DIR.glob("*.json")):
            with self.subTest(payload=payload_path.name):
                payload = json.loads(payload_path.read_text(encoding="utf-8"))
                validated = validate_task_input(payload)
                self.assertEqual(validated["source"], payload["source"])


if __name__ == "__main__":
    unittest.main()
