# Supervisor Input Specification

## 1. Purpose

This document defines the target input format accepted by `Supervisor`, based on the project specification in `plan/supervisor-spec.md`.

Its purpose is to standardize:

- the request structure accepted by `Supervisor`
- the required and optional fields
- the validation rules for input intake
- the handling of missing data
- the way requests are marked as requiring clarification before planning

## 2. Scope

This specification covers the normalized input model handled by the `Supervisor` intake layer after request ingestion from:

- `Jira`
- `chat`
- `API`

It does not define transport-specific webhook payloads or integration-specific adapters.

This specification also assumes an intake transformation step that converts the normalized request into a standardized working object for planning.

## 3. Design Principles

- The input contract must be explicit and type-driven.
- The input contract must preserve the source channel and operational context.
- The input contract must support validation before planning begins.
- Missing required information must be represented as structured clarification state, not hidden in free-form text.
- Requests that are incomplete must not proceed to planning.

## 4. Target Data Model

## 4.1 Top-Level Structure

The normalized input accepted by `Supervisor` is:

```json
{
  "request_id": "REQ-123",
  "source": "jira",
  "user_request": "Deploy service payments-api to stage",
  "params": {
    "target_environment": "stage",
    "priority": "high",
    "execution_params": {
      "service": "payments-api",
      "version": "2026.04.14",
      "change_window": "business-hours"
    }
  },
  "context": {
    "source_reference": "OPS-4321",
    "submitted_by": "devops.user",
    "conversation_ref": "jira-comment-17"
  },
  "intake": {
    "status": "ready_for_planning",
    "missing_fields": [],
    "invalid_fields": [],
    "clarification_questions": []
  }
}
```

## 4.2 Required Top-Level Fields

- `request_id`
- `source`
- `user_request`
- `params`

## 4.3 Top-Level Field Definitions

### `request_id`

Unique request identifier used to track the request across planning, policy evaluation, execution, and reporting.

Rules:

- required
- non-empty string
- must remain stable for the lifetime of the workflow

### `source`

The origin of the request.

Allowed values:

- `jira`
- `chat`
- `api`

Rules:

- required
- must match one of the supported source values

### `user_request`

The original task intent submitted by the user or upstream system.

Rules:

- required
- non-empty string after trimming
- should preserve the original user intent

### `params`

Structured execution-oriented metadata required for planning.

Rules:

- required
- must be an object
- must contain at least `target_environment` and `priority`

### `context`

Optional operational metadata carried with the request.

Rules:

- optional
- if present, must be an object

### `intake`

Structured intake assessment produced during normalization and validation.

Rules:

- required in the normalized Supervisor input
- represents whether the request is ready for planning or requires clarification

## 5. `params` Structure

## 5.1 Definition

The `params` object contains structured fields required by the planning layer.

```json
{
  "target_environment": "stage",
  "priority": "high",
  "execution_params": {
    "service": "payments-api",
    "version": "2026.04.14"
  }
}
```

## 5.2 Required Fields

### `target_environment`

Target environment for the requested operation.

Allowed values:

- `dev`
- `stage`
- `prod`

Rules:

- required
- must match a supported environment value

### `priority`

Operational priority used for planning and scheduling.

Allowed values:

- `low`
- `medium`
- `high`
- `urgent`

Rules:

- required
- must match a supported priority value

## 5.3 Optional Fields

### `execution_params`

Additional execution parameters needed for planning or downstream agents.

Rules:

- optional
- must be a key-value object
- values must be JSON-compatible
- may contain operational data such as service name, version, region, change window, or rollout mode

## 6. `context` Structure

The `context` object is used to preserve source-level metadata.

Example:

```json
{
  "source_reference": "OPS-4321",
  "submitted_by": "devops.user",
  "conversation_ref": "jira-comment-17"
}
```

Supported fields:

- `source_reference`: ticket id, message id, or API-side correlation id
- `submitted_by`: user or service identity
- `conversation_ref`: thread, comment, or interaction reference

All `context` fields are optional.

## 6.1 Derived Working Object

After normalization, the intake layer may derive a standardized working object for planning.

The working object should preserve the normalized request identity and add planning-oriented fields extracted from the request content and structured params.

Recommended fields:

- `service_name`: target service identifier when the task concerns an application or pipeline scope
- `target_environment`: final environment selected for the request
- `operation_type`: normalized operation such as deploy, rollback, infrastructure change, infrastructure provision, pipeline run, or pipeline validation
- `execution_params`: structured execution details such as version, region, rollout mode, or change window
- `constraints`: explicit execution constraints extracted from the request, such as no-downtime or time-window restrictions

The intake layer may populate these fields from:

- structured `params`
- structured `execution_params`
- direct extraction from `user_request` when the value is stated explicitly

The intake layer must not invent missing business values that are not clearly present in the request.

## 7. Intake Status and Clarification Marking

## 7.1 Purpose

Before planning starts, each request must be marked as either:

- ready for planning
- requiring clarification

This prevents incomplete requests from entering the planning stage.

## 7.2 Intake Structure

```json
{
  "status": "needs_clarification",
  "missing_fields": [
    "user_request"
  ],
  "invalid_fields": [
    "params.target_environment",
    "params.priority",
    "params.execution_params"
  ],
  "clarification_questions": [
    "What task should be performed?",
    "Which target environment should be used?",
    "What priority should be assigned to this request?",
    "Which execution parameters should be provided as a structured object?"
  ]
}
```

## 7.3 Allowed Intake Status Values

- `ready_for_planning`
- `needs_clarification`

## 7.4 Marking Rules

A request must be marked as `needs_clarification` if at least one required field is missing or empty:

- `request_id`
- `source`
- `user_request`
- `params`
- `params.target_environment`
- `params.priority`

The derived working object must also be marked as `needs_clarification` if planning-critical fields cannot be determined, especially:

- `operation_type`
- `service_name` for deployment-oriented or CI-oriented tasks

The request must also be marked as `needs_clarification` if:

- `user_request` is present but blank after trimming
- `params` exists but is not a valid object
- a required enumerated field contains an unsupported value and intake cannot safely normalize it
- an optional structured field required for safe normalization is present in an invalid format, for example `context` or `execution_params`

## 8. Validation Rules

## 8.1 Required Field Validation

The validation layer must check:

- presence of all required top-level fields
- presence of all required `params` fields
- string non-emptiness for textual required fields
- supported enumerated values for `source`, `target_environment`, and `priority`

## 8.2 Type Validation

The validation layer must enforce:

- `request_id` is a string
- `source` is a string that maps to a supported source
- `user_request` is a string
- `params` is an object
- `context`, if present, is an object
- `execution_params`, if present, is an object with JSON-compatible values

## 8.3 Normalization Rules

The intake layer may normalize:

- case for enumerated values such as `Jira` -> `jira`
- surrounding whitespace for string fields

The intake layer must not:

- invent missing business values
- infer missing environment or priority from speculation
- silently discard unsupported required field values

## 9. Missing Data Handling

## 9.1 Missing Required Fields

When required fields are missing, the request must not proceed to planning.

The system must:

- set `intake.status` to `needs_clarification`
- populate `intake.missing_fields`
- populate `intake.invalid_fields` when a provided field cannot be safely normalized
- generate `intake.clarification_questions`

## 9.2 Clarification Question Generation

Questions should be direct and field-specific.

Examples:

- missing `params.target_environment` -> `Which target environment should be used?`
- missing `params.priority` -> `What priority should be assigned to this request?`
- missing `user_request` -> `What task should be performed?`

## 9.3 Planning Gate Rule

Only requests with:

- `intake.status = ready_for_planning`

may enter the planning stage.

Requests with:

- `intake.status = needs_clarification`

must remain blocked until the missing information is provided and validation is rerun.

## 10. Recommended Logical Contract

```json
{
  "request_id": "REQ-123",
  "source": "jira",
  "user_request": "Deploy service payments-api to stage",
  "params": {
    "target_environment": "stage",
    "priority": "high",
    "execution_params": {
      "service": "payments-api",
      "version": "2026.04.14",
      "change_window": "business-hours"
    }
  },
  "context": {
    "source_reference": "OPS-4321",
    "submitted_by": "devops.user",
    "conversation_ref": "jira-comment-17"
  },
  "intake": {
    "status": "ready_for_planning",
    "missing_fields": [],
    "invalid_fields": [],
    "clarification_questions": []
  }
}
```

## 11. Acceptance Criteria

The specification is complete if:

- it defines a structure containing at least `user_request` and `params`
- it includes fields for request identifier, request source, target environment, priority, and additional execution parameters
- it defines validation rules for required fields and supported values
- it defines how missing data is handled
- it defines how requests are marked as requiring clarification before planning
- it remains aligned with `plan/supervisor-spec.md`
