from __future__ import annotations

import re
from typing import cast

from contracts.task_input_types import (
    Requester,
    SubmissionMetadata,
    SupervisorInput,
    TaskParameters,
    TaskSubmission,
)
from schema.task_input_schema import (
    ArrayField,
    BooleanField,
    CROSS_FIELD_RULES,
    CrossFieldRule,
    ExpectedValueRule,
    FieldDefinition,
    IntegerField,
    JsonValue,
    ObjectField,
    RequiredFieldInSetRule,
    RequiredFieldRule,
    SCHEMA_VERSION,
    StringField,
    TASK_INPUT_CONTRACT,
    export_task_input_schema,
    get_task_input_schema,
)


class ValidationError(ValueError):
    """Raised when the payload does not match the formal task contract."""


def validate_task_input(payload: object) -> TaskSubmission:
    """Validate required and optional fields for the external task payload."""
    normalized_payload = _validate_object(payload, TASK_INPUT_CONTRACT, "root")
    _validate_cross_field_rules(normalized_payload)
    return cast(TaskSubmission, normalized_payload)


def build_supervisor_input(submission: TaskSubmission) -> SupervisorInput:
    """Map validated external input to the supervisor contract from the specification."""
    return {
        "user_request": submission["taskDescription"],
        "params": submission.get("parameters", {}),
        "context": {
            "source": submission["source"],
            "requester": submission["requester"],
            "metadata": submission.get("metadata", {}),
            "schemaVersion": SCHEMA_VERSION,
        },
    }


def _validate_field(value: object, field_definition: FieldDefinition, field_path: str) -> JsonValue:
    if isinstance(field_definition, StringField):
        return _validate_string(value, field_definition, field_path)
    if isinstance(field_definition, BooleanField):
        return _validate_boolean(value, field_path)
    if isinstance(field_definition, IntegerField):
        return _validate_integer(value, field_definition, field_path)
    if isinstance(field_definition, ArrayField):
        return _validate_array(value, field_definition, field_path)
    return _validate_object(value, field_definition, field_path)


def _validate_object(value: object, field_definition: ObjectField, field_path: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        label = "Payload" if field_path == "root" else f"Field '{field_path}'"
        raise ValidationError(f"{label} must be a JSON object." if field_path == "root" else f"{label} must be an object.")

    if field_definition.min_properties is not None and len(value) < field_definition.min_properties:
        raise ValidationError(
            f"Field '{field_path}' must contain at least {field_definition.min_properties} propert"
            f"{'y' if field_definition.min_properties == 1 else 'ies'}."
        )

    unknown_fields = sorted(set(value) - set(field_definition.properties))
    if unknown_fields:
        unknown_fields_list = ", ".join(unknown_fields)
        raise ValidationError(f"Unknown field(s) in {field_path}: {unknown_fields_list}.")

    normalized: dict[str, JsonValue] = {}
    for required_field in sorted(field_definition.required):
        if required_field not in value:
            required_field_path = required_field if field_path == "root" else f"{field_path}.{required_field}"
            raise ValidationError(f"Field '{required_field_path}' is required.")

    for property_name, property_definition in field_definition.properties.items():
        if property_name not in value:
            continue
        property_path = property_name if field_path == "root" else f"{field_path}.{property_name}"
        normalized[property_name] = _validate_field(value[property_name], property_definition, property_path)
    return normalized


def _validate_string(value: object, field_definition: StringField, field_path: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"Field '{field_path}' must be a string.")

    normalized_value = value.strip()
    if len(normalized_value) == 0:
        raise ValidationError(f"Field '{field_path}' must be a non-empty string.")

    if field_definition.min_length is not None and len(normalized_value) < field_definition.min_length:
        raise ValidationError(
            f"Field '{field_path}' must be at least {field_definition.min_length} characters long."
        )

    if field_definition.max_length is not None and len(normalized_value) > field_definition.max_length:
        raise ValidationError(
            f"Field '{field_path}' must not exceed {field_definition.max_length} characters."
        )

    if field_definition.enum is not None and normalized_value not in field_definition.enum:
        allowed_values = ", ".join(field_definition.enum)
        raise ValidationError(f"Field '{field_path}' must be one of: {allowed_values}.")

    if field_definition.pattern is not None and re.fullmatch(field_definition.pattern, normalized_value) is None:
        raise ValidationError(f"Field '{field_path}' has an invalid format.")

    return normalized_value


def _validate_boolean(value: object, field_path: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError(f"Field '{field_path}' must be boolean when provided.")
    return value


def _validate_integer(value: object, field_definition: IntegerField, field_path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationError(f"Field '{field_path}' must be an integer.")

    if field_definition.minimum is not None and value < field_definition.minimum:
        raise ValidationError(
            f"Field '{field_path}' must be greater than or equal to {field_definition.minimum}."
        )

    if field_definition.maximum is not None and value > field_definition.maximum:
        raise ValidationError(
            f"Field '{field_path}' must be less than or equal to {field_definition.maximum}."
        )

    return value


def _validate_array(value: object, field_definition: ArrayField, field_path: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise ValidationError(f"Field '{field_path}' must be an array.")

    if field_definition.min_items is not None and len(value) < field_definition.min_items:
        raise ValidationError(f"Field '{field_path}' must contain at least {field_definition.min_items} entries.")

    if field_definition.max_items is not None and len(value) > field_definition.max_items:
        raise ValidationError(f"Field '{field_path}' must not contain more than {field_definition.max_items} entries.")

    normalized_items = [
        _validate_field(item, field_definition.items, f"{field_path}[{index}]")
        for index, item in enumerate(value)
    ]

    if field_definition.unique_items and len(set(normalized_items)) != len(normalized_items):
        raise ValidationError(f"Field '{field_path}' must not contain duplicates.")

    return normalized_items


def _validate_cross_field_rules(payload: dict[str, JsonValue]) -> None:
    for rule in CROSS_FIELD_RULES:
        if isinstance(rule, RequiredFieldRule):
            if _resolve_path(payload, rule.discriminator_path) == rule.discriminator_value and _resolve_path(
                payload, rule.required_path
            ) is None:
                raise ValidationError(rule.message)
            continue

        if isinstance(rule, RequiredFieldInSetRule):
            if _resolve_path(payload, rule.discriminator_path) in rule.discriminator_values and _resolve_path(
                payload, rule.required_path
            ) is None:
                raise ValidationError(rule.message)
            continue

        if _resolve_path(payload, rule.discriminator_path) == rule.discriminator_value and _resolve_path(
            payload, rule.expected_path
        ) != rule.expected_value:
            raise ValidationError(rule.message)


def _resolve_path(payload: dict[str, JsonValue], path: tuple[str, ...]) -> JsonValue:
    current_value: JsonValue = payload
    for path_segment in path:
        if not isinstance(current_value, dict) or path_segment not in current_value:
            return None
        current_value = current_value[path_segment]
    return current_value
