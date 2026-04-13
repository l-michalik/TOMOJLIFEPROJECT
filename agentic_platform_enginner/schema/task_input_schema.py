from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, TypeAlias

from agentic_platform_enginner.contracts.task_input_types import (
    EXECUTION_ENVIRONMENTS,
    REQUESTER_ROLES,
    SUBMISSION_SOURCES,
    TASK_OPERATIONS,
)


JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
JsonSchema = JsonObject

SCHEMA_VERSION: Final[str] = "1.0.0"
SCHEMA_PATH: Final[Path] = Path(__file__).resolve().parent.parent.joinpath(
    "docs", "task_input_schema.json"
)


@dataclass(frozen=True)
class StringField:
    description: str | None = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    enum: tuple[str, ...] | None = None


@dataclass(frozen=True)
class BooleanField:
    description: str | None = None


@dataclass(frozen=True)
class IntegerField:
    description: str | None = None
    minimum: int | None = None
    maximum: int | None = None


@dataclass(frozen=True)
class ArrayField:
    items: "FieldDefinition"
    description: str | None = None
    max_items: int | None = None
    unique_items: bool = False


@dataclass(frozen=True)
class ObjectField:
    properties: dict[str, "FieldDefinition"]
    description: str | None = None
    required: frozenset[str] = field(default_factory=frozenset)
    additional_properties: bool = False


FieldDefinition: TypeAlias = StringField | BooleanField | IntegerField | ArrayField | ObjectField


@dataclass(frozen=True)
class RequiredFieldRule:
    discriminator_path: tuple[str, ...]
    discriminator_value: str
    required_path: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class RequiredFieldInSetRule:
    discriminator_path: tuple[str, ...]
    discriminator_values: frozenset[str]
    required_path: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class ExpectedValueRule:
    discriminator_path: tuple[str, ...]
    discriminator_value: str
    expected_path: tuple[str, ...]
    expected_value: JsonValue
    message: str


CrossFieldRule: TypeAlias = RequiredFieldRule | RequiredFieldInSetRule | ExpectedValueRule


REQUESTER_FIELD: Final[ObjectField] = ObjectField(
    properties={
        "id": StringField(
            description="Identifier of the requesting user for audit purposes.",
            min_length=3,
            max_length=128,
        ),
        "role": StringField(
            description="Business or technical role of the user.",
            enum=REQUESTER_ROLES,
        ),
        "displayName": StringField(
            min_length=1,
            max_length=128,
        ),
    },
    required=frozenset({"id"}),
)

TASK_PARAMETERS_FIELD: Final[ObjectField] = ObjectField(
    properties={
        "environment": StringField(
            description="Target execution environment.",
            enum=EXECUTION_ENVIRONMENTS,
        ),
        "serviceName": StringField(
            min_length=2,
            max_length=128,
            pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$",
        ),
        "operation": StringField(
            description="Operation type handled by the system.",
            enum=TASK_OPERATIONS,
        ),
        "targetVersion": StringField(
            description="Artifact or release version to deploy.",
            min_length=1,
            max_length=64,
        ),
        "dryRun": BooleanField(
            description="Forces read-only or plan-only execution mode.",
        ),
        "approvalRequired": BooleanField(
            description="Explicit flag indicating that human approval is required.",
        ),
        "timeoutSeconds": IntegerField(
            minimum=30,
            maximum=86400,
        ),
        "tags": ArrayField(
            items=StringField(min_length=1, max_length=32),
            max_items=20,
            unique_items=True,
        ),
    }
)

METADATA_FIELD: Final[ObjectField] = ObjectField(
    properties={
        "ticketId": StringField(
            description="Jira ticket key when the request originates from Jira.",
            pattern=r"^[A-Z][A-Z0-9]+-\d+$",
        ),
        "threadId": StringField(
            description="Chat thread identifier when the request originates from chat.",
            min_length=1,
            max_length=128,
        ),
        "correlationId": StringField(
            description="Identifier used to trace the request across components.",
            min_length=8,
            max_length=128,
        ),
    }
)

TASK_INPUT_CONTRACT: Final[ObjectField] = ObjectField(
    properties={
        "taskDescription": StringField(
            description="Natural-language task description passed to the supervisor.",
            min_length=10,
            max_length=4000,
        ),
        "source": StringField(
            description="Channel from which the request originated.",
            enum=SUBMISSION_SOURCES,
        ),
        "requester": REQUESTER_FIELD,
        "parameters": TASK_PARAMETERS_FIELD,
        "metadata": METADATA_FIELD,
    },
    required=frozenset({"taskDescription", "source", "requester"}),
)

CROSS_FIELD_RULES: Final[tuple[CrossFieldRule, ...]] = (
    RequiredFieldRule(
        discriminator_path=("source",),
        discriminator_value="jira",
        required_path=("metadata", "ticketId"),
        message="Field 'metadata.ticketId' is required when source='jira'.",
    ),
    RequiredFieldRule(
        discriminator_path=("source",),
        discriminator_value="chat",
        required_path=("metadata", "threadId"),
        message="Field 'metadata.threadId' is required when source='chat'.",
    ),
    ExpectedValueRule(
        discriminator_path=("parameters", "environment"),
        discriminator_value="prod",
        expected_path=("parameters", "approvalRequired"),
        expected_value=True,
        message="Field 'parameters.approvalRequired' must be true for operations targeting 'prod'.",
    ),
    RequiredFieldInSetRule(
        discriminator_path=("parameters", "operation"),
        discriminator_values=frozenset({"deploy", "restart", "rollback"}),
        required_path=("parameters", "serviceName"),
        message="Field 'parameters.serviceName' is required for deploy, restart and rollback operations.",
    ),
    RequiredFieldRule(
        discriminator_path=("parameters", "operation"),
        discriminator_value="deploy",
        required_path=("parameters", "targetVersion"),
        message="Field 'parameters.targetVersion' is required for deploy operations.",
    ),
)


def get_task_input_schema() -> JsonSchema:
    """Return a copy of the JSON Schema for the system input."""
    return deepcopy(build_json_schema())


def export_task_input_schema(path: str | Path = SCHEMA_PATH) -> Path:
    """Persist the JSON Schema next to the project documentation."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(build_json_schema(), ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def build_json_schema() -> JsonSchema:
    schema = _field_to_json_schema(TASK_INPUT_CONTRACT)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "AgenticPlatformTaskSubmission"
    schema["description"] = (
        "Formal input schema for the Agentic Platform Engineer system "
        "for requests coming from Jira, chat, or API."
    )
    schema["allOf"] = [_cross_field_rule_to_json_schema(rule) for rule in CROSS_FIELD_RULES]
    return schema


def _field_to_json_schema(field_definition: FieldDefinition) -> JsonSchema:
    if isinstance(field_definition, StringField):
        schema: JsonSchema = {"type": "string"}
        if field_definition.description is not None:
            schema["description"] = field_definition.description
        if field_definition.min_length is not None:
            schema["minLength"] = field_definition.min_length
        if field_definition.max_length is not None:
            schema["maxLength"] = field_definition.max_length
        if field_definition.pattern is not None:
            schema["pattern"] = field_definition.pattern
        if field_definition.enum is not None:
            schema["enum"] = list(field_definition.enum)
        return schema

    if isinstance(field_definition, BooleanField):
        schema = {"type": "boolean"}
        if field_definition.description is not None:
            schema["description"] = field_definition.description
        return schema

    if isinstance(field_definition, IntegerField):
        schema = {"type": "integer"}
        if field_definition.description is not None:
            schema["description"] = field_definition.description
        if field_definition.minimum is not None:
            schema["minimum"] = field_definition.minimum
        if field_definition.maximum is not None:
            schema["maximum"] = field_definition.maximum
        return schema

    if isinstance(field_definition, ArrayField):
        schema = {
            "type": "array",
            "items": _field_to_json_schema(field_definition.items),
        }
        if field_definition.description is not None:
            schema["description"] = field_definition.description
        if field_definition.max_items is not None:
            schema["maxItems"] = field_definition.max_items
        if field_definition.unique_items:
            schema["uniqueItems"] = True
        return schema

    schema = {
        "type": "object",
        "additionalProperties": field_definition.additional_properties,
        "properties": {
            field_name: _field_to_json_schema(nested_definition)
            for field_name, nested_definition in field_definition.properties.items()
        },
    }
    if field_definition.description is not None:
        schema["description"] = field_definition.description
    if field_definition.required:
        schema["required"] = sorted(field_definition.required)
    return schema


def _cross_field_rule_to_json_schema(rule: CrossFieldRule) -> JsonSchema:
    if isinstance(rule, RequiredFieldRule):
        return {
            "if": _build_path_const_condition(rule.discriminator_path, rule.discriminator_value),
            "then": _build_required_path_schema(rule.required_path),
        }

    if isinstance(rule, RequiredFieldInSetRule):
        return {
            "if": _build_path_enum_condition(rule.discriminator_path, tuple(rule.discriminator_values)),
            "then": _build_required_path_schema(rule.required_path),
        }

    return {
        "if": _build_path_const_condition(rule.discriminator_path, rule.discriminator_value),
        "then": _build_expected_path_schema(rule.expected_path, rule.expected_value),
    }


def _build_path_const_condition(path: tuple[str, ...], value: JsonValue) -> JsonSchema:
    return _build_nested_object_schema(path, {"const": value})


def _build_path_enum_condition(path: tuple[str, ...], values: tuple[str, ...]) -> JsonSchema:
    return _build_nested_object_schema(path, {"enum": list(values)})


def _build_required_path_schema(path: tuple[str, ...]) -> JsonSchema:
    if len(path) == 1:
        return {"required": [path[0]]}
    head, *tail = path
    return {
        "required": [head],
        "properties": {
            head: _build_required_path_schema(tuple(tail)),
        },
    }


def _build_expected_path_schema(path: tuple[str, ...], value: JsonValue) -> JsonSchema:
    return _build_nested_object_schema(path, {"const": value}, require_terminal=True)


def _build_nested_object_schema(
    path: tuple[str, ...], terminal_schema: JsonSchema, *, require_terminal: bool = False
) -> JsonSchema:
    head, *tail = path
    if not tail:
        schema: JsonSchema = {"properties": {head: terminal_schema}}
        if require_terminal:
            schema["required"] = [head]
        return schema
    return {
        "required": [head],
        "properties": {
            head: _build_nested_object_schema(tuple(tail), terminal_schema, require_terminal=require_terminal),
        },
    }
