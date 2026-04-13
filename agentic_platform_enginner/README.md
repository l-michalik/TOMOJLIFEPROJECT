# Agentic Platform Engineer

This repository contains the formal system input contract derived from the project specification.

## Scope

The specification defines two input levels:

- external system input: `POST /api/tasks` with body `{"taskDescription": "...", "parameters": {...}}`
- normalized supervisor input: `{"user_request": "...", "params": {...}}`

This repository includes:

- formal JSON Schema: [docs/task_input_schema.json](/Users/lukaszmichalik/Documents/GitHub/TOMOJLIFEPROJECT/agentic_platform_enginner/docs/task_input_schema.json)
- schema source module: [schema/task_input_schema.py](/Users/lukaszmichalik/Documents/GitHub/TOMOJLIFEPROJECT/agentic_platform_enginner/schema/task_input_schema.py)
- Python validator: [schema/input_schema.py](/Users/lukaszmichalik/Documents/GitHub/TOMOJLIFEPROJECT/agentic_platform_enginner/schema/input_schema.py)
- typed payload definitions: [contracts/task_input_types.py](/Users/lukaszmichalik/Documents/GitHub/TOMOJLIFEPROJECT/agentic_platform_enginner/contracts/task_input_types.py)
- sample payloads: [examples/](/Users/lukaszmichalik/Documents/GitHub/TOMOJLIFEPROJECT/agentic_platform_enginner/examples)
- simple CLI for validation and normalization: [main.py](/Users/lukaszmichalik/Documents/GitHub/TOMOJLIFEPROJECT/agentic_platform_enginner/main.py)

## Required Fields

- `taskDescription`: task description, minimum 10 characters
- `source`: request source, one of `jira`, `chat`, `api`
- `requester.id`: identifier of the requesting user for audit purposes

## Optional Fields

- `requester.role`, `requester.displayName`
- `parameters.environment`: `dev`, `stage`, `prod`
- `parameters.serviceName`
- `parameters.operation`: `deploy`, `configure`, `diagnose`, `restart`, `rollback`, `provision`
- `parameters.targetVersion`
- `parameters.dryRun`
- `parameters.approvalRequired`
- `parameters.timeoutSeconds`
- `parameters.tags`
- `metadata.ticketId`, `metadata.threadId`, `metadata.correlationId`

## Validation Rules

- `metadata.ticketId` is required when `source="jira"`
- `metadata.threadId` is required when `source="chat"`
- for `parameters.environment="prod"`, `parameters.approvalRequired` must be set to `true`
- for `deploy`, `restart`, and `rollback` operations, `parameters.serviceName` is required
- for `deploy` operations, `parameters.targetVersion` is also required
- the schema rejects unknown fields through `additionalProperties=false`
- `parameters` and `metadata` cannot be empty objects when provided
- `parameters.tags` must contain at least one item when provided

## Sample Payloads

- Jira request: [examples/jira_payload.json](/Users/lukaszmichalik/Documents/GitHub/TOMOJLIFEPROJECT/agentic_platform_enginner/examples/jira_payload.json)
- Chat request: [examples/chat_payload.json](/Users/lukaszmichalik/Documents/GitHub/TOMOJLIFEPROJECT/agentic_platform_enginner/examples/chat_payload.json)
- Test/API request: [examples/api_test_payload.json](/Users/lukaszmichalik/Documents/GitHub/TOMOJLIFEPROJECT/agentic_platform_enginner/examples/api_test_payload.json)

## Usage

Run commands from the project directory:

```bash
cd agentic_platform_enginner
```

Print the schema:

```bash
uv run python main.py --print-schema
```

Validate a payload from file:

```bash
uv run python main.py --input examples/jira_payload.json
```

Validate and normalize to the supervisor contract:

```bash
uv run python main.py --input examples/chat_payload.json --normalize
```

Validate the test/API example:

```bash
uv run python main.py --input examples/api_test_payload.json
```

Run tests:

```bash
uv run python -m unittest discover -s tests
```
